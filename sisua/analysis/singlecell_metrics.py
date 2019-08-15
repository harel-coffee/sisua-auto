from __future__ import absolute_import, division, print_function

from abc import ABCMeta, abstractmethod
from numbers import Number
from typing import List, Union

import numpy as np
import tensorflow as tf
from six import add_metaclass
from tensorflow.python.keras.callbacks import Callback
from tensorflow_probability.python import distributions as tfd
from tensorflow_probability.python.distributions import Distribution

from odin.bay.distributions import ZeroInflated
from sisua.analysis.imputation_benchmarks import (correlation_scores,
                                                  imputation_mean_score,
                                                  imputation_score,
                                                  imputation_std_score)
from sisua.data import SingleCellOMICS
from sisua.models import SingleCellModel
from sisua.models.base import _to_sc_omics, _to_semisupervised_inputs

__all__ = [
    'SingleCellMetric', 'NegativeLogLikelihood', 'ImputationError',
    'Correlation'
]


def _preprocess_output_distribution(y_pred):
  if isinstance(y_pred, tfd.Independent) and \
    isinstance(y_pred.distribution, ZeroInflated):
    y_pred = tfd.Independent(
        y_pred.distribution.count_distribution,
        reinterpreted_batch_ndims=y_pred.reinterpreted_batch_ndims)
  return y_pred


# ===========================================================================
# Base class
# ===========================================================================
@add_metaclass(ABCMeta)
class SingleCellMetric(Callback):

  def __init__(self,
               inputs: Union[SingleCellOMICS, List[SingleCellOMICS], np.
                             ndarray, List[np.ndarray], None] = None,
               extras=None,
               n_samples=1,
               batch_size=128,
               verbose=0,
               name=None,
               **kwargs):
    super(SingleCellMetric, self).__init__(**kwargs)
    self.n_samples = n_samples
    self.batch_size = batch_size
    self.inputs = inputs
    self.extras = extras
    self.verbose = verbose
    self._name = name

  @property
  def name(self):
    return self.__class__.__name__.lower() if self._name is None else self._name

  def set_model(self, model: SingleCellModel):
    assert isinstance(
        model, SingleCellModel), "This callback only support SingleCellModel"
    self.model = model
    return self

  @abstractmethod
  def call(self, y_true: List[SingleCellOMICS], y_crpt: List[SingleCellOMICS],
           y_pred: List[Distribution], latents: List[Distribution], extras):
    raise NotImplementedError

  def __call__(self, inputs=None, n_samples=None):
    if inputs is None:
      inputs = self.inputs
    if n_samples is None:
      n_samples = self.n_samples
    model = self.model

    if not isinstance(inputs, (tuple, list)):
      inputs = [inputs]
    inputs = [_to_sc_omics(i) for i in inputs]
    if model.corruption_rate is not None:
      inputs_corrupt = [
          data.corrupt(corruption_rate=model.corruption_rate,
                       corruption_dist=model.corruption_dist,
                       inplace=False) if idx == 0 else data
          for idx, data in enumerate(inputs)
      ]
    else:
      inputs_corrupt = inputs

    outputs, latents = model.predict(inputs_corrupt,
                                     n_samples=self.n_samples,
                                     batch_size=self.batch_size,
                                     verbose=self.verbose,
                                     apply_corruption=False)
    if not isinstance(outputs, (tuple, list)):
      outputs = [outputs]
    if not isinstance(latents, (tuple, list)):
      latents = [latents]

    metrics = self.call(y_true=inputs,
                        y_pred=outputs,
                        y_crpt=inputs_corrupt,
                        latents=latents,
                        extras=self.extras)
    if metrics is None:
      metrics = {}
    elif tf.is_tensor(metrics) or \
      isinstance(metrics, np.ndarray) or \
        isinstance(metrics, Number):
      metrics = {self.name: metrics}
    assert isinstance(metrics, dict), \
      "Return metrics must be a dictionary mapping metric name to scalar value"
    metrics = {
        i: j.numpy() if tf.is_tensor(j) else j for i, j in metrics.items()
    }
    return metrics

  def on_epoch_end(self, epoch, logs=None):
    """Called at the end of an epoch.

    Subclasses should override for any actions to run. This function should only
    be called during TRAIN mode.

    Arguments:
        epoch: integer, index of epoch.
        logs: dict, metric results for this training epoch, and for the
          validation epoch if validation is performed. Validation result keys
          are prefixed with `val_`.
    """
    metrics = self()
    logs.update(metrics)


# ===========================================================================
# Losses
# ===========================================================================
class NegativeLogLikelihood(SingleCellMetric):
  """ Log likelihood metric """

  def call(self, y_true: List[SingleCellOMICS], y_crpt: List[SingleCellOMICS],
           y_pred: List[Distribution], latents: List[Distribution], extras):
    nllk = {}
    for idx, (t, p) in enumerate(zip(y_true, y_pred)):
      nllk['nllk%d' % idx] = -tf.reduce_mean(p.log_prob(t.X))
    return nllk


class ImputationError(SingleCellMetric):

  def call(self, y_true: List[SingleCellOMICS], y_crpt: List[SingleCellOMICS],
           y_pred: List[Distribution], latents: List[Distribution], extras):
    # only care about the first data input
    y_true = y_true[0]
    y_crpt = y_crpt[0]
    y_pred = y_pred[0]

    y_pred = _preprocess_output_distribution(y_pred)
    y_pred = y_pred.mean()
    if y_pred.shape.ndims == 3:
      y_pred = tf.reduce_mean(y_pred, axis=0)
    return {
        'imp_med':
            imputation_score(original=y_true.X, imputed=y_pred),
        'imp_mean':
            imputation_mean_score(original=y_true.X,
                                  corrupted=y_crpt.X,
                                  imputed=y_pred)
    }


class Correlation(SingleCellMetric):

  def call(self, y_true: List[SingleCellOMICS], y_crpt: List[SingleCellOMICS],
           y_pred: List[Distribution], latents: List[Distribution], extras):
    y_true = y_true[0]
    y_crpt = y_crpt[0]
    y_pred = y_pred[0]
    assert isinstance(extras, SingleCellOMICS), \
      "protein data must be provided as extras in form of SingleCellOMICS"
    protein = extras[y_true.indices]
    assert np.all(protein.obs['cellid'] == y_true.obs['cellid'])

    y_pred = _preprocess_output_distribution(y_pred)
    y_pred = y_pred.mean()
    if y_pred.shape.ndims == 3:
      y_pred = tf.reduce_mean(y_pred, axis=0)

    scores = correlation_scores(X=y_pred,
                                y=protein.X,
                                gene_name=y_true.var['geneid'],
                                protein_name=protein.var['protid'],
                                return_series=False)
    spearman = []
    pearson = []
    for _, (s, p) in scores.items():
      spearman.append(s)
      pearson.append(p)
    return {
        'pearson_mean': np.mean(pearson),
        'spearman_mean': np.mean(spearman),
        'pearson_med': np.median(pearson),
        'spearman_med': np.median(spearman),
    }
