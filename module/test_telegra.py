


import math
from typing import Callable, List, Union
from urllib.parse import unquote, urljoin, urlparse



import requests
from pyquery import PyQuery as pq



def parse_telegra_url(telegra_url: str) -> None:
        
        html_content = requests.get(telegra_url).text

        doc = pq(html_content)
        images = doc('img')

        telegra_images: List[List[str, str, int]] = []
        download_status = ('等待下载', '下载成功', '下载失败')
        msg = f"{telegra_url}\n"
        image_count_zero = int(math.log10(images.size())) + 1
        for i, item in enumerate(images.items()):
            src = item.attr('src')
            telegra_images.append([f"{i:0{image_count_zero}d}", urljoin(telegra_url, src), 0])
        print(telegra_images)
        return telegra_images
if __name__ == '__main__':
    # Example usage
    telegra_url = "https://telegra.ph/%E7%A7%80%E4%BA%BA%E7%BD%91-%E8%B0%A2%E5%B0%8F%E8%92%BD%E5%B9%BC%E5%B9%BC-%E6%9C%9B%E8%BF%9C%E9%95%9C%E5%81%B7%E7%AA%A5-04-06"
    parse_telegra_url(telegra_url)