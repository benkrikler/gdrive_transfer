from .drive import create, create_shortcut, ls
from .auth import get_credentials
import googleapiclient
from googleapiclient.discovery import build


def create_test_structure_1(dest_id):
    cred = get_credentials()
    with build('drive', 'v3', credentials=cred) as service:
        extra = {"gdrive_transfer_test-data": "This is a test"}
        top = create("Top level test directory", "folder", dest_id, extra=extra, service=service)["id"]
        one = create("Directory one", "folder", top, extra=extra, service=service)["id"]
        two = create("Directory Two", "folder", top, extra=extra, service=service)["id"]
        three = create("Directory three", "folder", two, extra=extra, service=service)["id"]
        four = create("Directory four", "folder", three, extra=extra, service=service)["id"]
        create("Doc a", "doc", top, extra=extra, service=service)
        doc_b = create("Doc b", "doc", one, extra=extra, service=service)
        create("Sheet c", "spreadsheet", two, extra=extra, service=service)
        create("Sheet d", "spreadsheet", three, extra=extra, service=service)
        create_shortcut(doc_b, two, extra=extra, service=service)

        ls(top)
        return top
