# inspired by https://github.com/SingularReza/drive-folder-copier/blob/master/final.py
import os
from .auth import get_credentials
import numpy as np
import pandas as pd
import json
import googleapiclient
from googleapiclient.discovery import build
import logging
logging.basicConfig(level=logging.INFO)


def __run(inner, service, *args, **kwargs):
    if service:
        return inner(service, *args, **kwargs)

    cred = get_credentials()
    with build('drive', 'v3', credentials=cred) as service:
        return inner(service, *args, **kwargs)


def get_records(file_id, recurse, service=None):
    records = []
    fields = "name id parents permissions mimeType appProperties".split(" ")
    def visit(service, fid, depth=0):
        file = service.files().get(fileId=fid,
                                   supportsAllDrives=True,
                                   fields="id,name,appProperties,parents,mimeType,permissions(emailAddress,id,role),owners").execute()
        record = {f: file.get(f) for f in fields}
        record["depth"] = depth
        record["shared_drive"] = "owners" not in file
        is_dir = file.get('mimeType') == 'application/vnd.google-apps.folder'
        record["is_dir"] = is_dir
        records.append(record)

        if not is_dir or not recurse:
            return
        children_req = service.files().list(
                                       q=f"'{fid}' in parents",
                                       includeItemsFromAllDrives=True,
                                       supportsAllDrives=True,
                                       fields="nextPageToken, files(id)")
        while children_req:
            children = children_req.execute()
            for child in children["files"]:
                visit(service, child.get("id"), depth + 1)
            children_req = service.files().list_next(children_req, children)

    __run(visit, service, file_id)
    return records


def ls(file_id, recurse=True, fmt="screen"):
    records = get_records(file_id, recurse)

    if fmt == "json":
        print(json.dumps(records))
    else:
        for file in records:
            prefix = "| "*file["depth"]
            perms = []
            if file["permissions"]:
                perms = [f"{x.get('emailAddress',x['id'])}: {x['role'][:3]}" for x in file["permissions"]]
            is_shared = "is_shared_drive" if file["shared_drive"] else "not_shared_drive"
            directory = "is_dir" if file["is_dir"] else "not_dir"
            print("{prefix}{name} ({id}) {perms} {appProperties} {is_shared} {directory}".format(**file, **locals()))


def is_shared_drive(file_id, service=None):
    def visit(service, fid):
        file = service.files().get(fileId=fid, supportsAllDrives=True, fields="owners").execute()
        return "owners" not in file
    return __run(visit, service, file_id)


def recursive_move(source_id, dest_id, dry_run=True, known_parents=None):
    logging.info(f"Move from: {source_id} to {dest_id}")
    cred = get_credentials()
    with build('drive', 'v3', credentials=cred) as service:
        result = _recursive_move(file_id=source_id, dest_folder_id=dest_id, service=service,
                                 dry_run=dry_run, known_parents=known_parents)
        return result


def check_unknown_parents(df, missing_parents=None):
    if missing_parents:
        missing_parents = {n: p if isinstance(p, list) else [p] for n, p in missing_parents.items()}
        df.parents = df.set_index("id").parents.fillna(missing_parents).values
    num_parents = df.parents.str.len()
    multiple_parents = num_parents.loc[num_parents > 1]
    if multiple_parents.empty:
        return df

    unstacked = pd.DataFrame({
        col:np.repeat(df[col].values, df["parents"].str.len())
        for col in df.columns.difference(["parents"])
        }).assign(**{"parents":np.concatenate(df["parents"].values)})[df.columns.tolist()]

    parents = (df[num_parents > 1].id).to_frame("id").merge(unstacked, how="left", on="id").parents.unique()
    missing_parents = np.setdiff1d(parents, df.id)
    if len(missing_parents):
        affected_files = unstacked.loc[unstacked.parents.isin(missing_parents)]
        logging.warning("Some items have more than one parent directory, of which at least one is unknown. Such items will lose the connection to that parent. Affected files are:")
        logging.warning(affected_files[["name", "id", "parents"]].to_string())
    return df


def _make_extras(file):
    extra = {"GDT-origId": file.id}

    for i, parent in enumerate(file.parents):
        extra[f"GDT-origParents-{i}"] = parent
    for i, permission in enumerate(file.permissions):
        who = permission.get("emailAddress", "anyone")
        role = permission.get("role")[:2]
        extra[f"GDT-origPerms-{i}"] = f"{who}={role}"
    for k, v in extra.items():
        s = len(k.encode('utf-8')) + len(v.encode('utf-8'))
        logging.debug(f"{k}: {v} = {s}")
    return extra


def _recursive_move(file_id, dest_folder_id, service, dry_run=True, known_parents=None):
    # Get file list
    file_list = pd.read_json(json.dumps(get_records(file_id, recurse=True, service=service)))
    file_list = check_unknown_parents(file_list, missing_parents=known_parents)

    tgt_is_shared_drive = is_shared_drive(dest_folder_id, service)
    if len(file_list) == 1 and not (file_list[0].is_dir and tgt_is_shared_drive):
        # Single file specified
        extra = _make_extras(file_list[0])
        return move_one(file_id, dest_folder_id, service, extra=extra)

    # clone directory tree
    directories = file_list.loc[file_list.is_dir].sort_values("depth")
    cache_name = f"{file_list.name[0]}_{file_list.id[0]}.json"

    if os.path.isfile(cache_name):
        with open(cache_name, "r") as cache_file:
            directory_mapping = json.load(cache_file)
    else: 
        directory_mapping = {directories.loc[0].parents[0]: dest_folder_id}
    for directory in directories.itertuples():
        if directory.id in directory_mapping:
            logging.info(f"Already exists: {directory.id} ({directory.name})")
            continue
        extra = _make_extras(directory)
        new_parent_ids = [directory_mapping[p] for p in directory.parents]
        new_dir = create(directory.name, filetype="folder", parent_id=new_parent_ids, extra=extra, service=service)
        directory_mapping[directory.id] = new_dir["id"]

    # cache directory_mapping in case of crash
    with open(cache_name, "w") as cache_file:
        cache_file.write(json.dumps(directory_mapping))

    # Move files over
    files = file_list.loc[~file_list.is_dir]
    bad_files = dict()
    for file in files.itertuples():
        extra = _make_extras(file)
        new_parent_ids = [directory_mapping[p] for p in file.parents if p in directory_mapping]
        try:
            move_one(file.id, new_parent_ids[0], service, extra=extra, dry_run=dry_run)
        except googleapiclient.errors.HttpError as e:
            bad_files[file.id] = str(e)
            logging.info(f"Problem moving file {file.id} ({file.name}): {e}")
            create_shortcut(file._asdict(), new_parent_ids[0], extra, service)
        for parent in new_parent_ids[1:]:
            create_shortcut(file._asdict(), parent, extra, service)
    return dict(mapping=directory_mapping, bad_files=bad_files)


def move_one(source_id, dest_folder_id, drive_service, extra=None, dry_run=True):
    logging.info(f"Moving a single file, {source_id}, to {dest_folder_id}")
    file = drive_service.files().get(fileId=source_id,
                                     fields='parents').execute()
    previous_parents = ",".join(file.get('parents'))

    update = dict(fileId=source_id,
                  body=dict(appProperties=extra),
                  addParents=dest_folder_id,
                  removeParents=previous_parents,
                  supportsAllDrives=True,
                  fields='id, parents, webViewLink'
                  )
    if dry_run:
        print(update)
    else:
        file = drive_service.files().update(**update).execute()
    return file


def create(name, filetype, parent_id=None, extra=None, service=None):
    logging.info(f"Creating '{name}' of type {filetype}")
    mimetypes = dict(doc="application/vnd.google-apps.document",
                     spreadsheet="application/vnd.google-apps.spreadsheet",
                     folder='application/vnd.google-apps.folder',
                     )
    assert filetype in mimetypes
    def inner(service, parent_id):
        file_metadata = {
                'name': name,
                'mimeType': mimetypes[filetype]
                }
        if extra:
            file_metadata["appProperties"] = extra
        if parent_id:
            if not isinstance(parent_id, list):
                parent_id = [parent_id]
            file_metadata['parents'] = parent_id

        logging.debug(f"{file_metadata=}")
        file = service.files().create(body=file_metadata,
                                      supportsAllDrives=True,
                                      fields='id,webViewLink').execute()
        return file

    return __run(inner, service, parent_id)


def create_shortcut(target_file, parent_id=None, extra=None, service=None):
    logging.info(f"Creating shortcut to '{target_file.get('id')}' in {parent_id}")
    def inner(service, parent_id):
        target = service.files().get(fileId=target_file["id"], supportsAllDrives=True).execute()
        if target["mimeType"] == 'application/vnd.google-apps.shortcut':
            file = service.files().copy(
                                fileId=target_file["id"],
                                body={"appProperties": extra} if extra else None,
                                supportsAllDrives=True
                                ).execute()
            return file
        file_metadata = {
                'name': target_file.get('name'),
                'mimeType': 'application/vnd.google-apps.shortcut',
                'shortcutDetails': {
                    'targetId': target_file.get('id')
                    }
                }
        if extra:
            file_metadata["appProperties"] = extra
        if parent_id:
            if not isinstance(parent_id, list):
                parent_id = [parent_id]
            file_metadata['parents'] = parent_id

        file = service.files().create(body=file_metadata,
                                      supportsAllDrives=True,
                                          fields='id,webViewLink').execute()
        return file
    return __run(inner, service, parent_id)


def transfer_ownership(target_id, service=None):
    logging.info(f"Transferring ownership on {target_id}")
    def inner(service):
        logging.info(service.permissions().list(fileId=target_id,
                                                  ).execute())
        permission = service.permissions().update(fileId=target_id,
                                                  transferOwnership=True,
                                                  body=dict(role="owner",
                                                            type="user",
                                                            emailAddress="mr.krikler@gmail.com")
                                                  ).execute()
    return __run(inner, service)


## Tests
# RecurseMove with: 
# - [ ] single file
# - [ ] between normal directories
# - [ ] single file with multiple parents that are contained in the directory structure
# - [ ] single file having multiple parents of which one or more are not in the directory structure
# - [ ] single file having multiple parents of which one or more are not in the directory structure
# - [ ] do we preserve existing appProperties?
