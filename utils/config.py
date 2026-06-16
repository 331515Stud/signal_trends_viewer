import os
import logging

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        filename="pipestreamDB_Viewer.log",
        filemode="w",
        format="%(asctime)s %(levelname)s %(message)s"
    )

def create_export_directory():
    os.makedirs("export", exist_ok=True)