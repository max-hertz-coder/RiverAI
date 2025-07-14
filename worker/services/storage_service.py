import aiohttp
from worker import config

async def upload_to_yadisk(token: str, file_path: str, remote_path: str):
    """
    Upload a file to Yandex Disk using API. remote_path is the path on Yandex.Disk.
    Returns True on success.
    """
    api_base = "https://cloud-api.yandex.net/v1/disk"
    headers = {"Authorization": f"OAuth {token}"}
    # Get upload URL
    async with aiohttp.ClientSession() as session:
        params = {"path": remote_path, "overwrite": "true"}
        async with session.get(f"{api_base}/resources/upload", headers=headers, params=params) as resp:
            if resp.status != 200:
                return False
            data = await resp.json()
            href = data.get("href")
            if not href:
                return False
        # Upload file by PUT
        async with session.put(href, data=open(file_path, 'rb')) as put_resp:
            return 200 <= put_resp.status < 300
