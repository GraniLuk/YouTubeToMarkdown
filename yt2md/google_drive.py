import os

from googleapiclient.http import MediaFileUpload


def upload_to_drive(service, file_path: str, folder_id: str = None) -> str:
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
