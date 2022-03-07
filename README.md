# gdrive_transfer

## Install
Dependencies are handled here via Poetry. See https://python-poetry.org/docs/#installation for setting that up.

Then to install and use this repository
```bash
cd <directory_containing_repo>
poetry install
poetry shell
```

Next you should make sure you've got necessary credentials to use the Drive api.
1. Create a API project on https://console.cloud.google.com
    - APIs + services > create project
2. Enable APIs & services > Enable Google Drive API, Google Docs API
3. Dashboard > Configure Consent screen > External
    - Add scopes: all Google Drive, all Google Docs
    - Add user: add your gmail account (you are not automatically a user!)
4. Create credentials - Dashboard > Credentials > + Create Credentials > OAuth 2.0 Client ID > Desktop App
    - Download json and place it where you intend to run the commands, or point the environmet variable GOOGLE_CREDENTIALS to the absolute path

This client ID file holds the credentials required to use the API, and must be accessed by the python program.

The first time you run in a while you'll have to authorize the app via a Google login page that should open

## Running
Use the CLI with:
```bash
python -m gdrive_transfer
```

### Examples
To move a directory recursively:
```
python -m gdrive_transfer -a mv -s <source_id> -d <dest_id> --actually-run
```

To get a json-based dump of the contents of a directory:
```
python -m gdrive_transfer -a ls_json -s <file_or_directory_id>
```

To create a testing directory structure:
```
python -m gdrive_transfer -a mk_test -s <parent_directory_id>
```
