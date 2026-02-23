import re
from typing import Optional, Tuple, List
from ..utils import get_logger

logger = get_logger('string_tools')

class StringTools:
    TYPE_A_LIST = ('CCTV1', 'CCTV4', 'CCTV5', 'CCTV8', 'CGTN')
    TYPE_B_LIST = (
        'CCTV10', 'CCTV11', 'CCTV12', 'CCTV13', 'CCTV14', 'CCTV15', 'CCTV16', 'CCTV17',
        'CCTV4K', 'CCTV4欧洲', 'CCTV4美洲', 'CCTV5+', 'CCTV8K',
        'CGTN法语', 'CGTN俄语', 'CGTN阿语', 'CGTN西语', 'CGTN记录'
    )
    
    @staticmethod
    def clean_channel_name(name: str) -> str:
        name = name.upper().replace(" ", "")
        
        match = re.search(r'(CCTV\d+[\+]?)', name)
        if match:
            return match.group(1)
        
        if "卫视" in name:
            return name.split("-")[0].replace("HD", "").replace("高清", "")
        
        return name
    
    @staticmethod
    def normalize_channel_name(name: str) -> str:
        name = name[:name.index('[')] if '[' in name else name
        name = name.replace("HD", "")
        name = name.replace("标清", "")
        name = name.replace("超高清", "4K")
        name = name.replace("高清", "")
        name = name.replace("超清", "")
        name = name.replace("#EXTINF-1", "")
        return name.strip()
    
    @staticmethod
    def match_category(channel_name: str, category_list: List[Tuple]) -> Optional[Tuple[str, str]]:
        for category_info in category_list:
            category_psw = category_info[0]
            category_name = category_info[1]
            category_type = category_info[2]
            
            name_values = category_psw.split(',')
            
            for name_value in name_values:
                if category_name in StringTools.TYPE_A_LIST:
                    if name_value in channel_name and not any(
                        type_b in channel_name for type_b in StringTools.TYPE_B_LIST
                    ):
                        return (category_name, category_type)
                else:
                    if name_value in channel_name:
                        return (category_name, category_type)
        
        return None
    
    @staticmethod
    def extract_m3u_links(line: str) -> List[str]:
        if not line:
            return []
        
        links = line.split('#')
        result = []
        
        for link in links:
            if "$" in link:
                link = link.split("$")[0]
            if link.strip():
                result.append(link.strip())
        
        return result
    
    @staticmethod
    def parse_channel_line(line: str) -> Optional[Tuple[str, str]]:
        if ',' not in line or 'http' not in line:
            return None
        
        parts = line.split(',', 1)
        if len(parts) == 2:
            name = parts[0].strip()
            url = parts[1].strip()
            return (name, url)
        
        return None
    
    @staticmethod
    def is_valid_channel_line(line: str) -> bool:
        if not line or ',' not in line:
            return False
        
        invalid_keywords = ['CAVS', '测试', '画中画', '单音轨']
        return not any(keyword in line for keyword in invalid_keywords)
