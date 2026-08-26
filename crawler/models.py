from dataclasses import dataclass
from typing import Dict, List, Optional, Set

# 網頁上 select name 對應的主要 PC 零組件分類
# Mapping of select element names to main PC component categories
MAIN_CATEGORIES: Dict[str, str] = {
    "n4": "處理器 CPU",
    "n5": "主機板 MB",
    "n6": "記憶體 RAM",
    "n7": "固態硬碟 M.2/SSD",
    "n8": "傳統硬碟 HDD",
    "n10": "散熱器",
    "n11": "水冷",
    "n12": "顯示卡 VGA",
    "n14": "機殼 CASE",
    "n15": "電源供應器 PSU",
}


def get_category_filter(fetch_all: bool) -> Optional[Set[str]]:
    """回傳要抓取的 select name 集合，None 表示全部抓取。
    Return the set of select names to scrape; None means scrape all."""
    if fetch_all:
        return None
    return set(MAIN_CATEGORIES.keys())


@dataclass
class Product:
    category: str
    subcategory: str
    name: str
    price: int
    remark: str  # 例如: 現貨、訂、客訂、限組裝，空字串表示無特殊標記 e.g. "搭機價", "客訂", "限組裝"; empty string if none


# CSV category 欄位（網站原始分類名）對應的 URL slug，用於靜態分類頁 /c/<slug>.html
# Maps the CSV category column (raw site labels) to URL slugs for /c/<slug>.html
CATEGORY_SLUGS: Dict[str, str] = {
    # 主要 PC 零組件 Main PC components
    "處理器 CPU": "cpu",
    "主機板 MB": "motherboard",
    "記憶體 RAM": "ram",
    "固態硬碟 M.2｜SSD": "ssd",
    "2.5/3.5 傳統內接硬碟HDD": "hdd",
    "散熱器｜散熱墊｜散熱膏": "cooler",
    "封閉式｜開放式水冷": "liquid-cooling",
    "顯示卡VGA": "vga",
    "CASE 機殼(+電源)": "case",
    "電源供應器": "psu",
    # 其餘分類（--all 模式）Remaining categories (--all mode)
    "螢幕｜投影機｜壁掛": "monitor",
    "鍵盤+鼠｜搖桿｜桌+椅": "keyboard-mouse",
    "筆電｜平板｜穿戴配件": "laptop-tablet",
    "滑鼠｜鼠墊｜數位板": "mouse",
    "機殼風扇｜機殼配件": "case-fan",
    "網路、傳輸線、轉頭｜KVM": "cable-kvm",
    "IP分享器｜網卡｜網通設備": "networking",
    "喇叭｜耳機｜麥克風": "audio",
    "隨身碟｜隨身硬碟｜記憶卡": "portable-storage",
    "品牌小主機、AIO｜VR虛擬": "mini-pc-aio",
    "USB週邊｜硬碟座｜讀卡機": "usb-peripheral",
    "網路NAS｜網路IPCAM": "nas-ipcam",
    "酷！PC 套裝產線": "prebuilt",
    "UPS不斷電｜印表機｜掃描": "ups-printer",
    "行車紀錄器｜USB視訊鏡頭": "dashcam-webcam",
    "OS+應用軟體｜禮物卡": "software",
    "介面擴充卡｜專業Raid卡": "expansion-card",
    "福利品出清": "clearance",
    "音效卡｜電視卡(盒)｜影音": "sound-tv-card",
    "燒錄器 CD/DVD/BD": "optical-drive",
}

# 分類頁的簡短說明，供 meta description 與頁面導言使用
# Short blurbs per category, used for meta description and page intro
CATEGORY_BLURBS: Dict[str, str] = {
    "cpu": "Intel Core 與 AMD Ryzen 處理器",
    "motherboard": "ASUS、MSI、GIGABYTE、ASRock 主機板",
    "ram": "DDR4／DDR5 桌上型記憶體",
    "ssd": "M.2 NVMe 與 2.5 吋 SATA 固態硬碟",
    "hdd": "2.5／3.5 吋內接傳統硬碟",
    "cooler": "塔式空冷散熱器、散熱墊與散熱膏",
    "liquid-cooling": "封閉式一體水冷與開放式水冷套件",
    "vga": "NVIDIA GeForce 與 AMD Radeon 顯示卡",
    "case": "電腦機殼與含電源機殼",
    "psu": "ATX 電源供應器",
    "monitor": "電腦螢幕、投影機與壁掛架",
    "keyboard-mouse": "鍵盤滑鼠組、搖桿與電競桌椅",
    "laptop-tablet": "筆記型電腦、平板與穿戴配件",
    "mouse": "滑鼠、滑鼠墊與繪圖板",
    "case-fan": "機殼風扇與機殼配件",
    "cable-kvm": "網路線、傳輸線、轉接頭與 KVM 切換器",
    "networking": "IP 分享器、網路卡與網通設備",
    "audio": "喇叭、耳機與麥克風",
    "portable-storage": "隨身碟、行動硬碟與記憶卡",
    "mini-pc-aio": "品牌小主機、AIO 一體機與 VR 裝置",
    "usb-peripheral": "USB 週邊、硬碟外接座與讀卡機",
    "nas-ipcam": "網路儲存 NAS 與網路攝影機",
    "prebuilt": "原價屋套裝電腦產線",
    "ups-printer": "UPS 不斷電系統、印表機與掃描器",
    "dashcam-webcam": "行車紀錄器與 USB 視訊鏡頭",
    "software": "作業系統、應用軟體與禮物卡",
    "expansion-card": "介面擴充卡與專業 RAID 卡",
    "clearance": "福利品與出清商品",
    "sound-tv-card": "音效卡、電視卡與影音設備",
    "optical-drive": "CD／DVD／BD 燒錄器",
}


# 導覽列與分類頁排序的優先順序：主要 PC 零組件排在周邊之前，其餘依商品數遞減
# Ordering priority for the nav bar and category listing: main PC components first,
# everything else by descending item count
PRIMARY_SLUGS: List[str] = [
    "cpu", "motherboard", "ram", "ssd", "hdd",
    "cooler", "liquid-cooling", "vga", "case", "psu",
]

# 導覽列用的短名稱，避免原始分類名過長撐爆版面
# Short labels for the nav bar, since raw category names are too long for it
CATEGORY_SHORT: Dict[str, str] = {
    "cpu": "CPU",
    "motherboard": "主機板",
    "ram": "記憶體",
    "ssd": "SSD",
    "hdd": "HDD",
    "cooler": "散熱器",
    "liquid-cooling": "水冷",
    "vga": "顯示卡",
    "case": "機殼",
    "psu": "電源",
    "monitor": "螢幕",
    "keyboard-mouse": "鍵鼠/桌椅",
    "laptop-tablet": "筆電/平板",
    "mouse": "滑鼠",
    "case-fan": "機殼風扇",
    "cable-kvm": "線材/KVM",
    "networking": "網通設備",
    "audio": "喇叭耳機",
    "portable-storage": "隨身儲存",
    "mini-pc-aio": "小主機/AIO",
    "usb-peripheral": "USB 週邊",
    "nas-ipcam": "NAS/IPCAM",
    "prebuilt": "套裝電腦",
    "ups-printer": "UPS/印表機",
    "dashcam-webcam": "行車/視訊",
    "software": "軟體",
    "expansion-card": "擴充卡",
    "clearance": "福利品",
    "sound-tv-card": "音效/電視卡",
    "optical-drive": "燒錄器",
}
