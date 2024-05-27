"""Data processing utilities for the first version of data processor."""

import gc
import os
import pickle
import shutil
from glob import glob

import numpy as np
import pandas as pd
import polars as pl
from tqdm.auto import tqdm

from ..config import COL_DATE, COL_ID, COL_WEEK, PATH_DATA, PATH_FEATURES
from . import utils


def gen_file_path(file_name: str, mode: str) -> str:
    """
    Generate data file path.

    Arguments:
        file_name: Name of the file.
        mode: train or test.
    Returns:
        path: Path to the file.
    """
    path = f"{PATH_DATA}/parquet_files/{mode}/{mode}_{file_name}.parquet"
    return path

def set_dtypes(schema: dict) -> dict:
    """
    Set dtypes for the columns in the DataFrame.

    Arguments:
        schema: A dictionary with column names as keys and dtypes as values.
    Returns:
        schema: A dictionary with column names as keys and changed dtypes as values.
    """
    for col, dtype in schema.items():
        if col in [COL_ID,COL_WEEK, "num_group1", "num_group2"]:
            schema[col] = pl.Int64
        elif col in [COL_DATE]:
            schema[col] = pl.Date
        elif col[-1] in ("P", "A"):
            schema[col] = pl.Float64
        elif col[-1] in ("M",):
            schema[col] = pl.String
        elif col[-1] in ("D",):
            schema[col] = pl.Date
        elif col[-1] in ("T", "L"):
            pass

    return schema

def write_data_props(dfs_props: dict, version: str = "old") -> None:
    """
    Write the properties of the DataFrames to a pickle file.

    Add information about:
        - paths to files with train and test data
        - schemas
        - categorical columns
        - changed column names

    Arguments:
        dfs_props: A dictionary containing the properties of the DataFrames.
        version: Version of the features configuration.
    """
    # Read features information
    features_df = pd.read_csv(
        os.path.join(PATH_FEATURES, f"features_{version}.csv")
    )
    features_df.fillna("", inplace=True)
    features_df.set_index("feature", inplace=True)

    dates_df = features_df[features_df["date_col"]==1]

    # Loop over data groups and write properties
    for name, props in tqdm(dfs_props.items()):
        features_sg_df = features_df[features_df["source_group"]==name]

        # Dictionary with unprocessed file names (patterns, example: 'applprev_1_*')
        file_names = props["paths"]
        # Initialize variables
        structure_dict = {
            i: {
                "paths": {"train": {}, "test": []}, # Actual paths to data files
                "schema": {}, # Schema of the raw file
                "columns_map": {} # Mapping of columns names
            }
            for i in file_names
        }
        # Column mappings are required to merge data from different sources.
        # If we have more than one source, we rename columns
        # from different sources to corresponding columns from
        # one of the sources ('a'). New names are set in features.csv
        columns = [] # List with columns
        cols_cat = {}
        columns_dtypes = {} # List with dtypes for all columns

        for file_name in file_names: # Loop over each file in the group
            for mode in ["train", "test"]: # Loop over modes
                # Get actual paths to files
                paths_i = glob(utils.gen_file_path(file_name, mode))
                paths_i = utils.sort_paths(paths_i)

                # Save schema from the first train file
                if mode == "train":
                    df = pl.read_parquet(paths_i[0])
                    schema = utils.set_dtypes(df.schema)
                    structure_dict[file_name]["schema"] = schema

            # Save columns, dtypes and mappings
            cols_to_incl = [] # List with columns
            cols_cat_i = {}
            cols_dtypes = {} # Dict with column dtypes
            mapping = {col: None for col in df.columns} # Column mapping
            for col in df.columns:
                # Create mapping
                if col in features_sg_df.index.values:
                    col_new = features_sg_df.loc[col]["new_name"]
                    mapping[col] = col_new if col_new else col
                    if features_df.loc[col]["agg"] == "dummy":
                        col_vals = [i for i in df[col].unique() if (i is not None) & (i != "")]
                        cols_cat_i.update({col: col_vals})
                else:
                    mapping[col] = col

                # Add column name
                cols_to_incl.append(mapping[col])

                # Add column dtype
                cols_dtypes.update({col: schema[col]})

            # Update columns and dtypes
            columns_dtypes.update(cols_dtypes)
            columns.extend(cols_to_incl)
            cols_cat.update(cols_cat_i)

            # Add mapping
            structure_dict[file_name]["columns_map"] = mapping

            del df
            gc.collect()
        columns = np.unique(columns)

        # Update props
        props["structure"] = structure_dict
        props["columns"] = columns
        props["columns_cat"] = cols_cat
        props["columns_dtypes"] = columns_dtypes
        props["columns_date_index"] = dates_df[dates_df["source_group"]==name].index.to_list()

    # Save
    with open(os.path.join(PATH_FEATURES, f"dfs_props_{version}.pkl"), 'wb') as handle:
        pickle.dump(dfs_props, handle)

def sort_paths(paths: list) -> list:
    """
    Sort paths to homecredit files.

    Arguments:
        paths (list): list of paths. Each path should be in the format {name}_{n}.
    Returns:
        sorted_paths (list): sorted list of paths.
    """
    if len(paths) == 1:
        return paths
    else:
        paths_nums = [int(path.split("_")[-1].split(".")[0]) for path in paths]
        sorted_paths = [path for _, path in sorted(zip(paths_nums, paths))]
        return sorted_paths

def create_folder(path: str, rm: bool = False) -> None:
    """
    Create a folder with os.makedirs.

    Arguments:
        path (str): Path to the folder.
        rm (bool): Whether to remove path if it exists.
    """
    if rm:
        if os.path.exists(path):
            shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)

def get_features_df(dfs_props, version: str = "old") -> dict:
    """
    Loads and processes the features configuration from a CSV file.

    Returns:
        dict: A dictionary where keys are feature names and values are dictionaries of feature properties.
    """
    # Read csv with feature information
    features_df = pd.read_csv(
        os.path.join(PATH_FEATURES, f"features_{version}.csv"),
        index_col=0,
    )
    features_df = features_df[features_df["source_group"].isin(dfs_props.keys())]
    features_df.fillna("", inplace=True)

    return features_df
