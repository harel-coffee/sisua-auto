from __future__ import absolute_import, division, print_function

import copy
import os
from collections import OrderedDict
from numbers import Number
from typing import Tuple

import numpy as np

from odin.stats import describe, sparsity_percentage, train_valid_test_split
from odin.utils import cache_memory, ctext, one_hot
from sisua.data import normalization_recipes
from sisua.data.const import UNIVERSAL_RANDOM_SEED
from sisua.data.single_cell_dataset import (SingleCellOMICS,
                                            apply_artificial_corruption,
                                            get_library_size)
from sisua.data.utils import (get_gene_id2name, standardize_protein_name,
                              validating_dataset)


def get_dataset_meta():
  """
  Return
  ------
  dictionary : dataset name -> loading_function()
  """
  from sisua.data.data_loader.pbmc_CITEseq import read_CITEseq_PBMC
  from sisua.data.data_loader.pbmc10x_pp import read_10xPBMC_PP
  from sisua.data.data_loader.cbmc_CITEseq import read_CITEseq_CBMC
  from sisua.data.data_loader.mnist import read_MNIST
  from sisua.data.data_loader.facs_gene_protein import read_FACS, read_full_FACS
  from sisua.data.data_loader.fashion_mnist import (read_fashion_MNIST,
                                                    read_fashion_MNIST_drop,
                                                    read_MNIST_drop)
  from sisua.data.data_loader.scvi_datasets import (read_Cortex, read_Hemato,
                                                    read_PBMC, read_Retina)
  from sisua.data.data_loader.pbmc8k import read_PBMC8k
  from sisua.data.data_loader.pbmcecc import read_PBMCeec
  from sisua.data.experimental_data.pbmc_8k_ecc_ly import (
      read_PBMCcross_ecc_8k, read_PBMCcross_remove_protein)
  from sisua.data.data_loader.centenarian import read_centenarian
  data_meta = {
      "centenarian":
          read_centenarian,
      # ====== PBMC 10x ====== #
      # TODO: fix error with PBMC-scVAE
      # 'pbmcscvae': read_10xPBMC_PP,
      'pbmcscvi':
          read_PBMC,

      # ====== pbmc 8k ====== #
      'pbmc8klyfull':
          lambda override: read_PBMC8k(
              subset='ly', override=override, filtered_genes=False),
      'pbmc8kmyfull':
          lambda override: read_PBMC8k(
              subset='my', override=override, filtered_genes=False),
      'pbmc8kly':
          lambda override: read_PBMC8k(
              subset='ly', override=override, filtered_genes=True),
      'pbmc8kmy':
          lambda override: read_PBMC8k(
              subset='my', override=override, filtered_genes=True),
      'pbmc8k':
          lambda override: read_PBMC8k(
              subset='full', override=override, filtered_genes=True),
      'pbmc8kfull':
          lambda override: read_PBMC8k(
              subset='full', override=override, filtered_genes=False),

      # ====== PBMC ECC ====== #
      'pbmcecclyfull':
          lambda override: read_PBMCeec(
              subset='ly', override=override, filtered_genes=False),
      # 'pbmcecc_myfull': lambda override: read_PBMCeec(subset='my', override=override, filtered_genes=False),
      'pbmceccly':
          lambda override: read_PBMCeec(
              subset='ly', override=override, filtered_genes=True),
      # 'pbmcecc_my': lambda override: read_PBMCeec(subset='my', override=override, filtered_genes=True),
      # 'pbmcecc': lambda override: read_PBMCeec(subset='full', override=override, filtered_genes=True),
      # 'pbmcecc_full': lambda override: read_PBMCeec(subset='full', override=override, filtered_genes=False),

      # ====== cross PBMC ====== #
      'cross8klyfull':
          lambda override: read_PBMCcross_ecc_8k(subset='ly',
                                                 return_ecc=False,
                                                 override=override,
                                                 filtered_genes=False),
      'cross8kly':
          lambda override: read_PBMCcross_ecc_8k(subset='ly',
                                                 return_ecc=False,
                                                 override=override,
                                                 filtered_genes=True),
      'crossecclyfull':
          lambda override: read_PBMCcross_ecc_8k(subset='ly',
                                                 return_ecc=True,
                                                 override=override,
                                                 filtered_genes=False),
      'crosseccly':
          lambda override: read_PBMCcross_ecc_8k(subset='ly',
                                                 return_ecc=True,
                                                 override=override,
                                                 filtered_genes=True),
      'cross8knocd4':
          lambda override: read_PBMCcross_remove_protein(subset='ly',
                                                         return_ecc=False,
                                                         override=override,
                                                         filtered_genes=True,
                                                         remove_protein='CD4'),
      'crosseccnocd4':
          lambda override: read_PBMCcross_remove_protein(subset='ly',
                                                         return_ecc=True,
                                                         override=override,
                                                         filtered_genes=True,
                                                         remove_protein='CD4'),
      'cross8knocd8':
          lambda override: read_PBMCcross_remove_protein(subset='ly',
                                                         return_ecc=False,
                                                         override=override,
                                                         filtered_genes=True,
                                                         remove_protein='CD8'),
      'crosseccnocd8':
          lambda override: read_PBMCcross_remove_protein(subset='ly',
                                                         return_ecc=True,
                                                         override=override,
                                                         filtered_genes=True,
                                                         remove_protein='CD8'),
      'cross8knocd48':
          lambda override: read_PBMCcross_remove_protein(subset='ly',
                                                         return_ecc=False,
                                                         override=override,
                                                         filtered_genes=True,
                                                         remove_protein=
                                                         ['CD4', 'CD8']),
      'crosseccnocd48':
          lambda override: read_PBMCcross_remove_protein(subset='ly',
                                                         return_ecc=True,
                                                         override=override,
                                                         filtered_genes=True,
                                                         remove_protein=
                                                         ['CD4', 'CD8']),
      'cross8konlycd8':
          lambda override: read_PBMCcross_remove_protein(
              subset='ly',
              return_ecc=False,
              override=override,
              filtered_genes=True,
              remove_protein=['CD3', 'CD4', 'CD16', 'CD56', 'CD19']),
      # ====== CITEseq ====== #
      'pbmcciteseq':
          read_CITEseq_PBMC,
      'cbmcciteseq':
          read_CITEseq_CBMC,
      'pbmc5000':
          lambda override: read_CITEseq_PBMC(override, version_5000genes=True),

      # ====== MNIST ====== #
      'mnist':
          read_MNIST,
      'mnistorg':
          read_MNIST,
      'mnistimp':
          read_MNIST_drop,
      'fmnist':
          read_fashion_MNIST,
      'fmnistorg':
          read_fashion_MNIST,
      'fmnistimp':
          read_fashion_MNIST_drop,

      # ====== FACS ====== #
      'facs7':
          lambda override: read_full_FACS(override=override),
      'facs5':
          lambda override: read_FACS(n_protein=5, override=override),
      'facs2':
          lambda override: read_FACS(n_protein=2, override=override),

      # ====== other fun ====== #
      'cortex':
          read_Cortex,
      'retina':
          read_Retina,
      'hemato':
          read_Hemato,
  }
  import re
  pattern = re.compile('\w*')
  for name in data_meta.keys():
    assert pattern.match(name) and '_' not in name
  return data_meta


def get_dataset_summary(return_html=False):
  from sisua.data.utils import standardize_protein_name
  all_datasets = []
  for name, fn in sorted(get_dataset_meta().items()):
    ds = fn(override=False)
    info = OrderedDict([
        ('Keyword', name),
        ('#Cells', ds['X'].shape[0]),
        ('#Genes', ds['X'].shape[1]),
        ('#Labels', ds['y'].shape[1]),
        ('Binary', sorted(np.unique(ds['y'].astype('float32'))) == [0., 1.]),
        ('Labels', ', '.join([standardize_protein_name(i) for i in ds['y_col']
                             ])),
    ])
    all_datasets.append(info)
  df = pd.DataFrame(all_datasets)
  if return_html:
    return df.to_html()
  return df


def get_dataset(dataset_name,
                override=False) -> Tuple[SingleCellOMICS, SingleCellOMICS]:
  """ Check `get_dataset_meta` for more information

  Return
  ------
  dataset: `odin.fuel.dataset.Dataset` contains original data
  """
  data_meta = get_dataset_meta()
  # ====== special case: get all dataset ====== #
  dataset_name = str(dataset_name).lower().strip()
  if dataset_name not in data_meta:
    raise RuntimeError(
        'Cannot find dataset with name: "%s", all dataset include: %s' %
        (dataset_name, ",".join(list(data_meta.keys()))))
  ds = data_meta[dataset_name](override=override)
  validating_dataset(ds)
  # ******************** return ******************** #
  x = SingleCellOMICS(X=ds['X'],
                      obs={'cellid': ds['X_row']},
                      var={'geneid': ds['X_col']},
                      name=dataset_name)
  y = SingleCellOMICS(X=ds['y'],
                      obs={'cellid': ds['X_row']},
                      var={'protid': ds['y_col']},
                      name=dataset_name)
  return x, y


def get_scvi_dataset(dataset_name):
  """ Convert any SISUA dataset to relevant format for scVI models """
  from scvi.dataset import GeneExpressionDataset
  ds, gene, prot = get_dataset(dataset_name, override=False)
  X = np.concatenate((gene.X_train, gene.X_test), axis=0)
  labels = np.concatenate((prot.X_train, prot.X_test), axis=0)
  means, vars = get_library_size(X)
  is_multi_classes_labels = np.all(np.sum(labels, axis=1) != 1.)
  scvi = GeneExpressionDataset(X=X,
                               local_means=means,
                               local_vars=vars,
                               batch_indices=np.zeros(shape=(X.shape[0], 1)),
                               labels=None,
                               gene_names=gene.X_col,
                               cell_types=None)
  if not is_multi_classes_labels:
    scvi.labels = labels
    scvi.cell_types = prot.X_col
  else:
    scvi.labels = labels
    scvi.adt_expression = labels
    scvi.protein_markers = prot.X_col
  return scvi


# ===========================================================================
# Some shortcut
# ===========================================================================
def Cortex():
  return get_dataset('cortex')[0]


def PBMCscVI():
  """ The PBMC dataset used in scVI paper """
  return get_dataset('pbmcscvi')[0]


def PBMCscVAE():
  """ The PBMC dataset used in scVAE paper """
  return get_dataset('pbmcscvae')[0]


# ====== PBMC 8k ====== #
def PBMC8k_lymphoid(filtered_genes=True):
  """ lymphoid subset of PBMC 8k"""
  return get_dataset('pbmc8k_ly' if filtered_genes else 'pbmc8k_lyfull')[0]


def PBMC8k_myeloid(filtered_genes=True):
  """ myeloid subset of PBMC 8k"""
  return get_dataset('pbmc8k_my' if filtered_genes else 'pbmc8k_myfull')[0]


def PBMC8k(filtered_genes=True):
  """ PBMC 8k """
  return get_dataset('pbmc8k' if filtered_genes else 'pbmc8k_full')[0]


# ====== PBMC ecc ====== #
def PBMCecc_lymphoid(filtered_genes=True):
  """ lymphoid subset of PBMC ecc"""
  return get_dataset('pbmcecc_ly' if filtered_genes else 'pbmcecc_lyfull')[0]


def PBMCecc_myeloid(filtered_genes=True):
  """ myeloid subset of PBMC ecc"""
  return get_dataset('pbmcecc_my' if filtered_genes else 'pbmcecc_myfull')[0]


def PBMCecc(filtered_genes=True):
  """ PBMC ecc"""
  return get_dataset('pbmcecc' if filtered_genes else 'pbmcecc_full')[0]


# ====== cross dataset ====== #
def CROSS8k_lymphoid(filtered_genes=True):
  return get_dataset('cross8k_ly' if filtered_genes else 'cross8k_lyfull')[0]


def CROSSecc_lymphoid(filtered_genes=True):
  return get_dataset('crossecc_ly' if filtered_genes else 'crossecc_lyfull')[0]


# ====== cross dataset without specific proteins ====== #
def CROSS8k_noCD4():
  return get_dataset('cross8k_nocd4')[0]


def CROSS8k_noCD8():
  return get_dataset('cross8k_nocd8')[0]


def CROSS8k_noCD48():
  return get_dataset('cross8k_nocd48')[0]
