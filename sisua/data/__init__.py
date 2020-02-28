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
from sisua.data.const import OMIC, UNIVERSAL_RANDOM_SEED
from sisua.data.path import CONFIG_PATH, DATA_DIR, EXP_DIR
from sisua.data.single_cell_dataset import (SingleCellOMIC,
                                            apply_artificial_corruption,
                                            get_library_size)
from sisua.data.utils import (get_gene_id2name, is_binary_dtype,
                              is_categorical_dtype, standardize_protein_name,
                              validating_dataset)


def get_dataset_meta():
  """
  Return
  ------
  dictionary : dataset name -> loading_function()
  """
  from sisua.data.data_loader.dataset10x import read_dataset10x_cellexp
  from sisua.data.data_loader.pbmc_CITEseq import read_CITEseq_PBMC
  from sisua.data.data_loader.cbmc_CITEseq import read_CITEseq_CBMC
  from sisua.data.data_loader.mnist import read_MNIST
  from sisua.data.data_loader.fashion_mnist import read_fashion_MNIST
  from sisua.data.data_loader.facs_gene_protein import read_FACS, read_full_FACS
  from sisua.data.data_loader.scvi_datasets import (read_Cortex, read_Hemato,
                                                    read_PBMC, read_Retina)
  from sisua.data.data_loader.pbmc8k import read_PBMC8k
  from sisua.data.data_loader.pbmcecc import read_PBMCeec
  from sisua.data.experimental_data.pbmc_8k_ecc_ly import (
      read_PBMCcross_ecc_8k, read_PBMCcross_remove_protein)
  from sisua.data.data_loader.centenarian import read_centenarian
  data_meta = {
      "100yo":
          read_centenarian,
      # ====== PBMC 10x ====== #
      "neuron10k":
          lambda override=False, verbose=False: read_dataset10x_cellexp(
              name='neuron_10k_v3',
              spec='filtered',
              override=override,
              verbose=verbose),
      "heart10kv3":
          lambda override=False, verbose=False: read_dataset10x_cellexp(
              name='heart_10k_v3',
              spec='filtered',
              override=override,
              verbose=verbose),
      "cellvdj":
          lambda override=False, verbose=False: read_dataset10x_cellexp(
              name='cellvdj',
              spec='filtered',
              override=override,
              verbose=verbose),
      'memoryt':
          lambda override=False, verbose=False: read_dataset10x_cellexp(
              name='memory_t',
              spec='filtered',
              override=override,
              verbose=verbose),
      '5k':
          lambda override=False, verbose=False: read_dataset10x_cellexp(
              name='5k_pbmc_protein_v3',
              spec='filtered',
              override=override,
              verbose=verbose),
      '5kgem':
          lambda override=False, verbose=False: read_dataset10x_cellexp(
              name='5k_pbmc_protein_v3_nextgem',
              spec='filtered',
              override=override,
              verbose=verbose),

      # ====== pbmc 8k ====== #
      '8klyall':
          lambda override=False, verbose=False: read_PBMC8k(subset='ly',
                                                            override=override,
                                                            verbose=verbose,
                                                            filtered_genes=False
                                                           ),
      '8kmyall':
          lambda override=False, verbose=False: read_PBMC8k(subset='my',
                                                            override=override,
                                                            verbose=verbose,
                                                            filtered_genes=False
                                                           ),
      '8kly':
          lambda override=False, verbose=False: read_PBMC8k(subset='ly',
                                                            override=override,
                                                            verbose=verbose,
                                                            filtered_genes=True
                                                           ),
      '8kmy':
          lambda override=False, verbose=False: read_PBMC8k(subset='my',
                                                            override=override,
                                                            verbose=verbose,
                                                            filtered_genes=True
                                                           ),
      '8k':
          lambda override=False, verbose=False: read_PBMC8k(subset='full',
                                                            override=override,
                                                            verbose=verbose,
                                                            filtered_genes=True
                                                           ),
      '8kall':
          lambda override=False, verbose=False: read_PBMC8k(subset='full',
                                                            override=override,
                                                            verbose=verbose,
                                                            filtered_genes=False
                                                           ),

      # ====== PBMC ECC ====== #
      'ecclyall':
          lambda override=False, verbose=False: read_PBMCeec(subset='ly',
                                                             override=override,
                                                             verbose=verbose,
                                                             filtered_genes=
                                                             False),
      'eccly':
          lambda override=False, verbose=False: read_PBMCeec(subset='ly',
                                                             override=override,
                                                             verbose=verbose,
                                                             filtered_genes=True
                                                            ),
      'eccmyall':
          lambda override: read_PBMCeec(subset='my',
                                        override=override,
                                        verbose=verbose,
                                        filtered_genes=False),
      'eccmy':
          lambda override: read_PBMCeec(subset='my',
                                        override=override,
                                        verbose=verbose,
                                        filtered_genes=True),
      'ecc':
          lambda override: read_PBMCeec(subset='full',
                                        override=override,
                                        verbose=verbose,
                                        filtered_genes=True),
      'eccall':
          lambda override: read_PBMCeec(subset='full',
                                        override=override,
                                        verbose=verbose,
                                        filtered_genes=False),

      # ====== cross PBMC ====== #
      '8klyallx':
          lambda override=False, verbose=False: read_PBMCcross_ecc_8k(
              subset='ly',
              return_ecc=False,
              override=override,
              verbose=verbose,
              filtered_genes=False),
      '8klyx':
          lambda override=False, verbose=False: read_PBMCcross_ecc_8k(
              subset='ly',
              return_ecc=False,
              override=override,
              verbose=verbose,
              filtered_genes=True),
      'ecclyallx':
          lambda override=False, verbose=False: read_PBMCcross_ecc_8k(
              subset='ly',
              return_ecc=True,
              override=override,
              verbose=verbose,
              filtered_genes=False),
      'ecclyx':
          lambda override=False, verbose=False: read_PBMCcross_ecc_8k(
              subset='ly',
              return_ecc=True,
              override=override,
              verbose=verbose,
              filtered_genes=True),
      '8knocd4x':
          lambda override=False, verbose=False: read_PBMCcross_remove_protein(
              subset='ly',
              return_ecc=False,
              override=override,
              verbose=verbose,
              filtered_genes=True,
              remove_protein='CD4'),
      'eccnocd4x':
          lambda override=False, verbose=False: read_PBMCcross_remove_protein(
              subset='ly',
              return_ecc=True,
              override=override,
              verbose=verbose,
              filtered_genes=True,
              remove_protein='CD4'),
      '8knocd8x':
          lambda override=False, verbose=False: read_PBMCcross_remove_protein(
              subset='ly',
              return_ecc=False,
              override=override,
              verbose=verbose,
              filtered_genes=True,
              remove_protein='CD8'),
      'eccnocd8x':
          lambda override=False, verbose=False: read_PBMCcross_remove_protein(
              subset='ly',
              return_ecc=True,
              override=override,
              verbose=verbose,
              filtered_genes=True,
              remove_protein='CD8'),
      '8knocd48x':
          lambda override=False, verbose=False: read_PBMCcross_remove_protein(
              subset='ly',
              return_ecc=False,
              override=override,
              verbose=verbose,
              filtered_genes=True,
              remove_protein=['CD4', 'CD8']),
      'eccnocd48x':
          lambda override=False, verbose=False: read_PBMCcross_remove_protein(
              subset='ly',
              return_ecc=True,
              override=override,
              filtered_genes=True,
              remove_protein=['CD4', 'CD8']),
      '8konlycd8x':
          lambda override=False, verbose=False: read_PBMCcross_remove_protein(
              subset='ly',
              return_ecc=False,
              override=override,
              verbose=verbose,
              filtered_genes=True,
              remove_protein=['CD3', 'CD4', 'CD16', 'CD56', 'CD19']),
      # ====== CITEseq ====== #
      'pbmcciteseq':
          read_CITEseq_PBMC,
      'cbmcciteseq':
          read_CITEseq_CBMC,
      'pbmc5000':
          lambda override=False, verbose=False: read_CITEseq_PBMC(
              override=override, verbose=verbose, version_5000genes=True),

      # ====== MNIST ====== #
      'mnist':
          read_MNIST,
      'fmnist':
          read_fashion_MNIST,

      # ====== FACS ====== #
      'facs7':
          lambda override=False, verbose=False: read_full_FACS(
              override=override, verbose=verbose),
      'facs5':
          lambda override=False, verbose=False: read_FACS(
              n_protein=5, override=override, verbose=verbose),
      'facs2':
          lambda override=False, verbose=False: read_FACS(
              n_protein=2, override=override, verbose=verbose),

      # ====== other fun ====== #
      'pbmcscvi':
          read_PBMC,
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


def get_dataset(dataset_name, override=False, verbose=False) -> SingleCellOMIC:
  r""" Check `get_dataset_meta` for more information

  Return:
    mRNA data : `SingleCellOMIC`
    label data: `SingleCellOMIC`. If label data is not availabel, then None

  Example:
    gene, prot = get_dataset("cortex")
    X_train, X_test = gene.split(0.8, seed=1234)
    y_train, y_test = prot.split(0.8, seed=1234)
    X_train.assert_matching_cells(y_train)
    X_test.assert_matching_cells(y_test)
  """
  data_meta = get_dataset_meta()
  # ====== special case: get all dataset ====== #
  dataset_name = str(dataset_name).lower().strip()
  if dataset_name not in data_meta:
    raise RuntimeError(
        'Cannot find dataset with name: "%s", all dataset include: %s' %
        (dataset_name, ", ".join(list(data_meta.keys()))))
  ds = data_meta[dataset_name](override=override, verbose=verbose)
  validating_dataset(ds)
  # ******************** return ******************** #
  # var['genename'] = ds['X_col_name']
  # var['protname'] = ds['y_col_name']
  sc = SingleCellOMIC(X=ds['X'],
                      cell_id=ds['X_row'],
                      gene_id=ds['X_col'],
                      name=dataset_name)
  if 'y' in ds:
    y = ds['y']
    if is_binary_dtype(y):
      sc.add_omic(OMIC.celltype, y, ds['y_col'])
    else:
      sc.add_omic(OMIC.proteomic, y, ds['y_col'])
  return sc


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
