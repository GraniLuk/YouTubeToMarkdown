import os
import pickle

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def upload_to_drive(service, file_path: str, folder_id: str) -> str:
    """
    Upload a file to Google Drive

    Args:
        service: Google Drive API service instance
        file_path (str): Path to the file to upload
        folder_id (str): Optional Google Drive folder ID

    Returns:
        str: ID of the uploaded file
    """
    file_metadata = {
        "name": os.path.basename(file_path),
        "parents": [folder_id] if folder_id else [],
    }

    media = MediaFileUpload(file_path, mimetype="text/markdown", resumable=True)

    file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )

    return file.get("id")


def setup_google_drive():
    """
    Sets up Google Drive API credentials
    Returns:
        Google Drive API service
    """
    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    creds = None
    script_dir = get_script_dir()
    token_path = os.path.join(script_dir, "token.pickle")
    credentials_path = os.path.join(script_dir, "credentials.json")

    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                os.remove(token_path)
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=8080)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(
                port=8080, access_type="offline", include_granted_scopes="true"
            )
        # Save the credentials for the next run
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return build("drive", "v3", credentials=creds)


def get_script_dir() -> str:
    """
    Get the directory where the script is located
    """
    return os.path.dirname(os.path.abspath(__file__))
