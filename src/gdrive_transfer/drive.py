# inspired by https://github.com/SingularReza/drive-folder-copier/blob/master/final.py
from .auth import get_credentials
import pandas as pd
import json
import googleapiclient
from googleapiclient.discovery import build


def get_records(file_id, recurse):
    records = []
    fields = "name id parents permissions appProperties".split(" ")
    def visit(fid, service, depth=0):
        file = service.files().get(fileId=fid,
                                   supportsAllDrives=True,
                                   fields="id,name,appProperties,parents,mimeType,permissions(emailAddress,id,role),owners").execute()
        record = {f: file.get(f) for f in fields}
        record["depth"] = depth
        record["shared_drive"] = "owners" not in file
        is_dir = file.get('mimeType') == 'application/vnd.google-apps.folder'
        record["is_dir"] = is_dir
        records.append(record)

        if recurse and is_dir:
                children = service.files().list(
                                               q=f"'{fid}' in parents",
                                              fields="nextPageToken, files(id)").execute()
                for child in children["files"]:
                    visit(child.get("id"), service, depth + 1)

    cred = get_credentials()
    with build('drive', 'v3', credentials=cred) as service:
        visit(file_id, service)

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
    def visit(fid, service, depth=0):
        file = service.files().get(fileId=fid, supportsAllDrives=True, fields="owners").execute()
        return "owners" not in file

    if service:
        return visit(file_id, service)

    cred = get_credentials()
    with build('drive', 'v3', credentials=cred) as service:
        return visit(file_id, service)


def create_folder(name, parent_id=None, extra=None, service=None):
    def inner():
        file_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder'
                }
        if meta:
            file_metadata["appProperties"] = extra
        if parent_id:
            if not isinstance(parent_id, list):
                parent_id = [parent_id]
            file_metadata['parents'] = parent_id

        file = service.files().create(body=file_metadata,
                                      supportsAllDrives=True,
                                      fields='id,webViewLink').execute()
        return file

    if service:
        return inner()

    cred = get_credentials()
    with build('drive', 'v3', credentials=cred) as service:
        return inner()


def recursive_move(source_id, dest_id):
    cred = get_credentials()
    with build('drive', 'v3', credentials=cred) as service:
        changed_dirs = _recursive_move(file_id=source_id, dest_folder_id=dest_id, service=service)
        print(json.dumps(changed_dirs))
        return changed_dirs


def check_unknown_parents(file_list):
    num_parents = file_list.parents.str.len()
    multiple_parents = num_parents.loc[num_parents > 1]
    if multiple_parents.empty:
        return

    unstacked = pd.DataFrame({
        col:np.repeat(df[col].values, df["parents"].str.len())
        for col in df.columns.difference(["parents"])
        }).assign(**{"parents":np.concatenate(df["parents"].values)})[df.columns.tolist()]

    parents = (df[length > 1].id).to_frame("id").merge(unstacked, how="left", on="id").parents.unique()
    missing_parents = np.setdiff1d(parents, df.id)
    if len(missing_parents):
        affected_files = unstacked.loc[unstacked.parents.isin(missing_parents)]
        print("Some items have more than one parent directory, of which at least one is unknown. Such items will lose the connection to that parent. Affected files are:")
        print(affected_files[["name", "id", "parents"]].to_string())


def _make_extras(file):
    return {"gdrive_transfer-originalId": file.id,
            "gdrive_transfer-originalParents": file.parents,
            "gdrive_transfer-originalPermissions": file.permissions}


def _recursive_move(file_id, dest_folder_id, service):
    # Get file list
    file_list = pd.from_json(get_records(file_id, recurse=True))
    check_unknown_parents(file_list)

    tgt_is_shared_drive = is_shared_drive(dest_folder_id, service)
    if len(file_list) == 1 and not (file_list[0].is_dir and tgt_is_shared_drive):
        # Single file specified
        extra = make_extras(file_list[0])
        return move_one(file_id, dest_folder_id, service, extra=extra)

    # clone directory tree
    directories = file_list.loc[file_list.is_dir].sort_values("depth")
    directory_mapping = {directories[0].parents: dest_folder_id}
    for directory in directories.itertuples():
        extra = make_extras(directory)
        new_parent_ids = [directory_mapping[p] for p in directory.parents]
        new_dir = create_folder(directory.name, parent_id=new_parent_ids, extra=extra, service=service)
        directory_mapping[directory.id] = new_dir.id

    # Move files over
    files = file_list.loc[~file_list.is_dir]
    for file in files.itertuples():
        extra = make_extras(file)
        new_parent_ids = [directory_mapping[p] for p in file.parents]
        move_one(file.id, ",".join(new_parent_ids), service, extra=extra)
    return directory_mapping


def move_one(source_id, dest_folder_id, drive_service, extra=None):
    file = drive_service.files().get(fileId=source_id,
                                     fields='parents').execute()
    previous_parents = ",".join(file.get('parents'))

    file = drive_service.files().update(fileId=source_id,
                                        appProperties=extra
                                        addParents=dest_folder_id,
                                        removeParents=previous_parents,
                                        supportsAllDrives=True,
                                        fields='id, parents, webViewLink').execute()
    return file

## Tests
# RecurseMove with: 
# - [ ] single file
# - [ ] between normal directories
# - [ ] single file with multiple parents that are contained in the directory structure
# - [ ] single file having multiple parents of which one or more are not in the directory structure
# - [ ] single file having multiple parents of which one or more are not in the directory structure
