"""provide upload cloud drive"""
import asyncio
import functools
import importlib
import inspect
import os
import pathlib
import re
from asyncio import subprocess
from subprocess import Popen
from typing import Callable
from zipfile import ZipFile

from loguru import logger

from utils import platform


# pylint: disable = R0902
class CloudDriveConfig:
    """Rclone Config"""

    def __init__(
        self,
        enable_upload_file: bool = False,
        before_upload_file_zip: bool = False,
        after_upload_file_delete: bool = True,
        rclone_path: str = os.path.join(
            os.path.abspath("."), "rclone", f"rclone{platform.get_exe_ext()}"
        ),
        remote_dir: str = "",
        upload_adapter: str = "rclone",
    ):
        self.enable_upload_file = enable_upload_file
        self.before_upload_file_zip = before_upload_file_zip
        self.after_upload_file_delete = after_upload_file_delete
        self.rclone_path = rclone_path
        self.remote_dir = remote_dir
        self.upload_adapter = upload_adapter
        self.dir_cache: dict = {}  # for remote mkdir
        self.total_upload_success_file_count = 0
        self.aligo = None

    def pre_run(self):
        """pre run init aligo"""
        if self.enable_upload_file and self.upload_adapter == "aligo":
            CloudDrive.init_upload_adapter(self)


class CloudDrive:
    """rclone support"""

    @staticmethod
    def init_upload_adapter(drive_config: CloudDriveConfig):
        """Initialize the upload adapter."""
        if drive_config.upload_adapter == "aligo":
            Aligo = importlib.import_module("aligo").Aligo
            drive_config.aligo = Aligo()

    @staticmethod
    def rclone_mkdir(drive_config: CloudDriveConfig, remote_dir: str):
        """mkdir in remote"""
        with Popen(
            f'"{drive_config.rclone_path}" mkdir "{remote_dir}/"',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ):
            pass

    @staticmethod
    def aligo_mkdir(drive_config: CloudDriveConfig, remote_dir: str):
        """mkdir in remote by aligo"""
        if drive_config.aligo and not drive_config.aligo.get_folder_by_path(remote_dir):
            drive_config.aligo.create_folder(name=remote_dir, check_name_mode="refuse")

    @staticmethod
    def zip_file(local_file_path: str) -> str:
        """
        Zip local file
        """

        file_path_without_extension = os.path.splitext(local_file_path)[0]
        zip_file_name = file_path_without_extension + ".zip"

        with ZipFile(zip_file_name, "w") as zip_writer:
            zip_writer.write(local_file_path)

        return zip_file_name

    # pylint: disable = R0914
    @staticmethod
    async def rclone_upload_file(
        drive_config: CloudDriveConfig,
        save_path: str,
        local_file_path: str,
        progress_callback: Callable = None,
        progress_args: tuple = (),
    ) -> bool:
        """Use Rclone upload file"""
        upload_status: bool = False
        try:
            # remote_dir = (
            #     drive_config.remote_dir
            #     + "/"
            #     + os.path.dirname(os.path.abspath(local_file_path)).replace(os.path.abspath(save_path), "")
            #     + "/"
            # ).replace("\\", "/")
            
            remote_dir = drive_config.remote_dir + "/" + pathlib.Path(local_file_path).absolute().relative_to(pathlib.Path(save_path).absolute()).parent.as_posix()
            if not drive_config.dir_cache.get(remote_dir):
                CloudDrive.rclone_mkdir(drive_config, remote_dir)
                drive_config.dir_cache[remote_dir] = True

            zip_file_path: str = ""
            file_path = local_file_path
            if drive_config.before_upload_file_zip:
                zip_file_path = CloudDrive.zip_file(local_file_path)
                file_path = zip_file_path
            else:
                file_path = local_file_path

            cmd = (
                f'"{drive_config.rclone_path}" copy "{file_path}" '
                f'"{remote_dir}/" --create-empty-src-dirs --ignore-existing --progress'
            )
            proc = await asyncio.create_subprocess_shell(
                cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            if proc.stdout:
                async for output in proc.stdout:
                    s = output.decode(errors="replace")
                    print(s)
                    if "Transferred" in s and "100%" in s and "1 / 1" in s:
                        logger.info(f"upload file {local_file_path} success")
                        drive_config.total_upload_success_file_count += 1
                        if drive_config.after_upload_file_delete:
                            os.remove(local_file_path)
                        if drive_config.before_upload_file_zip:
                            os.remove(zip_file_path)
                        upload_status = True
                    else:
                        pattern = (
                            r"Transferred: (.*?) / (.*?), (.*?)%, (.*?/s)?, ETA (.*?)$"
                        )
                        transferred_match = re.search(pattern, s)

                        if transferred_match:
                            if progress_callback:
                                func = functools.partial(
                                    progress_callback,
                                    transferred_match.group(1),
                                    transferred_match.group(2),
                                    transferred_match.group(3),
                                    transferred_match.group(4),
                                    transferred_match.group(5),
                                    *progress_args,
                                )

                            if inspect.iscoroutinefunction(progress_callback):
                                await func()

            await proc.wait()
        except Exception as e:
            logger.error(f"{e.__class__} {e}")
            return False

        return upload_status

    @staticmethod
    def aligo_upload_file(
        drive_config: CloudDriveConfig, save_path: str, local_file_path: str
    ):
        """aliyun upload file"""
        upload_status: bool = False
        if not drive_config.aligo:
            logger.warning("please config aligo! see README.md")
            return False

        try:
            remote_dir = (
                drive_config.remote_dir
                + "/"
                + os.path.dirname(local_file_path).replace(save_path, "")
                + "/"
            ).replace("\\", "/")

            if not drive_config.dir_cache.get(remote_dir):
                CloudDrive.aligo_mkdir(drive_config, remote_dir)
                aligo_dir = drive_config.aligo.get_folder_by_path(remote_dir)
                if aligo_dir:
                    drive_config.dir_cache[remote_dir] = aligo_dir.file_id

            zip_file_path: str = ""
            file_paths = []
            if drive_config.before_upload_file_zip:
                zip_file_path = CloudDrive.zip_file(local_file_path)
                file_paths.append(zip_file_path)
            else:
                file_paths.append(local_file_path)

            res = drive_config.aligo.upload_files(
                file_paths=file_paths,
                parent_file_id=drive_config.dir_cache[remote_dir],
                check_name_mode="refuse",
            )

            if len(res) > 0:
                drive_config.total_upload_success_file_count += len(res)
                if drive_config.after_upload_file_delete:
                    os.remove(local_file_path)

                if drive_config.before_upload_file_zip:
                    os.remove(zip_file_path)

                upload_status = True

        except Exception as e:
            logger.error(f"{e.__class__} {e}")
            return False

        return upload_status

    @staticmethod
    async def upload_file(
        drive_config: CloudDriveConfig, save_path: str, local_file_path: str
    ) -> bool:
        """Upload file
        Parameters
        ----------
        drive_config: CloudDriveConfig
            see @CloudDriveConfig

        save_path: str
            Local file save path config

        local_file_path: str
            Local file path

        Returns
        -------
        bool
            True or False
        """
        if not drive_config.enable_upload_file:
            return False

        ret: bool = False
        if drive_config.upload_adapter == "rclone":
            ret = await CloudDrive.rclone_upload_file(
                drive_config, save_path, local_file_path
            )
        elif drive_config.upload_adapter == "aligo":
            ret = CloudDrive.aligo_upload_file(drive_config, save_path, local_file_path)

        return ret
