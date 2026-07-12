"""
kegg_api.py — ชั้นสื่อสารกับ KEGG REST API

หน้าที่: เรียก KEGG server, retry เมื่อ network ล้ม, และ cache ผลกันเรียกซ้ำ
หลักการ: ชั้นนี้ "ไม่พูด" (ไม่มี print) และไม่ผูกกับ UI ใด ๆ
         ถ้าเกิดปัญหา จะคืน dict/list ว่าง หรือส่งต่อผ่าน error callback
         ให้ชั้นบน (core → CLI/GUI) เป็นผู้ตัดสินใจรายงาน

การ cache:
- ใช้ dict ในหน่วยความจำ ต่อ 1 instance ของ KeggClient (คือ 1 การรัน)
- POS และ NEG มีสารซ้ำกันมาก (เช่น กรดไขมันที่เจอทั้งสอง mode)
  cache จึงตัดการยิง API ซ้ำได้จริง และรอบสองในรันเดียวกันจะเร็วขึ้นมาก
"""

import time
import requests

from . import config


class KeggClient:
    """
    client สำหรับคุยกับ KEGG REST API พร้อม cache + retry

    ตัวอย่างการใช้:
        client = KeggClient()
        info = client.get_compound("C00114")
        hits = client.find_by_name("Choline")

    พารามิเตอร์ที่ override ได้ (ปกติใช้ค่าจาก config):
        base_url, delay, timeout, max_retries, retry_backoff
        on_network_error: callback(message:str) เรียกเมื่อเกิด network error
                          (ให้ชั้นบนเอาไป log/แสดงผลเอง; ถ้าไม่ส่งมาก็เงียบ)
    """

    def __init__(
        self,
        base_url: str = config.KEGG_BASE,
        delay: float = config.API_DELAY,
        timeout: int = config.API_TIMEOUT,
        max_retries: int = config.API_MAX_RETRIES,
        retry_backoff: float = config.API_RETRY_BACKOFF,
        on_network_error=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.on_network_error = on_network_error

        # cache แยกตามชนิดการเรียก เพื่อไม่ให้ key ชนกัน
        self._compound_cache: dict[str, dict] = {}
        self._find_cache: dict[str, list] = {}

        # สถิติไว้ให้ชั้นบนดึงไป log ได้ (ไม่เก็บข้อมูล compound เพื่อ privacy)
        self.stats = {
            "compound_api_calls": 0,
            "compound_cache_hits": 0,
            "find_api_calls": 0,
            "find_cache_hits": 0,
            "network_errors": 0,
        }

    # --------------------------------------------------------------
    # helper: ยิง GET พร้อม retry + backoff
    # --------------------------------------------------------------
    def _get_with_retry(self, url: str) -> requests.Response | None:
        """
        ยิง GET request พร้อม retry
        คืน Response object ถ้าสำเร็จ (status 200), คืน None ถ้าล้มเหลวทุกครั้ง
        """
        last_err = None
        for attempt in range(1, self.max_retries + 1):
            try:
                r = requests.get(url, timeout=self.timeout)
                if r.status_code == 200:
                    return r
                # status ไม่ใช่ 200 (เช่น 404 = ไม่พบ) ไม่ใช่ error ที่ควร retry
                if r.status_code == 404:
                    return None
                last_err = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                last_err = str(e)

            # ถ้ายังไม่ใช่รอบสุดท้าย ให้หน่วงแล้วลองใหม่ (backoff เพิ่มขึ้นเรื่อย ๆ)
            if attempt < self.max_retries:
                time.sleep(self.retry_backoff * attempt)

        # ล้มเหลวทุกรอบ
        self.stats["network_errors"] += 1
        if self.on_network_error:
            self.on_network_error(f"KEGG request failed after {self.max_retries} retries: {last_err}")
        return None

    # --------------------------------------------------------------
    # ดึงข้อมูล compound จาก C number
    # --------------------------------------------------------------
    def get_compound(self, cid: str) -> dict:
        """
        ดึงข้อมูล compound จาก KEGG ด้วย C number
        คืน dict: {"kegg_name", "kegg_formula", "kegg_exact_mass"}
        ค่าที่หาไม่เจอจะเป็น None
        """
        cid = cid.strip()
        empty = {"kegg_name": None, "kegg_formula": None, "kegg_exact_mass": None}

        if not cid:
            return dict(empty)

        # เช็ค cache ก่อน
        if cid in self._compound_cache:
            self.stats["compound_cache_hits"] += 1
            return dict(self._compound_cache[cid])  # คืน copy กัน mutate

        url = f"{self.base_url}/get/{cid}"
        r = self._get_with_retry(url)
        self.stats["compound_api_calls"] += 1
        time.sleep(self.delay)

        if r is None:
            # ไม่ cache ผลที่ล้มเหลว เผื่อ retry รอบหน้าได้
            return dict(empty)

        info = dict(empty)
        for line in r.text.splitlines():
            if line.startswith("NAME"):
                name_line = line.replace("NAME", "", 1).strip()
                info["kegg_name"] = name_line.rstrip(";").strip()
            elif line.startswith("FORMULA"):
                info["kegg_formula"] = line.replace("FORMULA", "", 1).strip()
            elif line.startswith("EXACT_MASS"):
                try:
                    info["kegg_exact_mass"] = float(line.replace("EXACT_MASS", "", 1).strip())
                except ValueError:
                    pass

        self._compound_cache[cid] = dict(info)
        return info

    # --------------------------------------------------------------
    # ค้นหา compound จากชื่อ
    # --------------------------------------------------------------
    def find_by_name(self, name: str) -> list:
        """
        ค้นหา KEGG compound จากชื่อ
        คืน list ของ dict: [{"cid": "C00114", "names": "Choline; ..."}, ...]
        ไม่พบ → คืน list ว่าง
        """
        name = name.strip()
        if not name:
            return []

        # เช็ค cache (ใช้ชื่อตัวพิมพ์เดิมเป็น key)
        if name in self._find_cache:
            self.stats["find_cache_hits"] += 1
            return [dict(h) for h in self._find_cache[name]]

        safe_name = requests.utils.quote(name, safe="")
        url = f"{self.base_url}/find/compound/{safe_name}"
        r = self._get_with_retry(url)
        self.stats["find_api_calls"] += 1
        time.sleep(self.delay)

        if r is None or not r.text.strip():
            # cache ผล "ไม่พบ" ได้ เพราะชื่อเดิมยังไงก็ไม่พบซ้ำในรันเดียวกัน
            # (แต่ถ้าเป็น network error r จะเป็น None → ไม่ cache เผื่อ retry)
            if r is not None:
                self._find_cache[name] = []
            return []

        hits = []
        for line in r.text.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                cid = parts[0].replace("cpd:", "")
                hits.append({"cid": cid, "names": parts[1]})

        self._find_cache[name] = [dict(h) for h in hits]
        return hits
