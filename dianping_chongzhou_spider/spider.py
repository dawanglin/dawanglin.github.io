#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import random
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

CHONGZHOU_KEYWORDS = ["崇州", "崇阳", "羊马", "街子", "元通", "怀远"]


@dataclass
class Shop:
    shop_id: str
    name: str
    category: str
    address: str
    district: str
    score: str
    review_count: str
    avg_price: str
    detail_url: str


class DianpingSpider:
    def __init__(self) -> None:
        load_dotenv()
        self.db_path = Path(os.getenv("DB_PATH", "./data/chongzhou_shops.db"))
        self.output_csv = Path(os.getenv("OUTPUT_CSV", "./data/chongzhou_shops.csv"))
        self.timeout = int(os.getenv("REQUEST_TIMEOUT", "15"))
        self.min_sleep = float(os.getenv("MIN_SLEEP_SECONDS", "1.0"))
        self.max_sleep = float(os.getenv("MAX_SLEEP_SECONDS", "2.2"))
        self.cookie = os.getenv("DIANPING_COOKIE", "")
        urls = os.getenv("CHANNEL_URLS", "")
        self.channel_urls = [u.strip() for u in urls.split(";") if u.strip()]
        self.max_pages = int(os.getenv("MAX_PAGES_PER_CHANNEL", "2"))
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://www.dianping.com/chengdu",
            }
        )
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie

    def init_storage(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_csv.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shops (
                shop_id TEXT PRIMARY KEY,
                name TEXT,
                category TEXT,
                address TEXT,
                district TEXT,
                score TEXT,
                review_count TEXT,
                avg_price TEXT,
                detail_url TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        conn.close()

    def fetch(self, url: str) -> str:
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        delay = random.uniform(self.min_sleep, self.max_sleep)
        time.sleep(delay)
        return resp.text

    def iter_listing_urls(self) -> Iterable[str]:
        for base in self.channel_urls:
            yield base
            for page in range(2, self.max_pages + 1):
                suffix = f"p{page}"
                if base.endswith("/"):
                    yield f"{base}{suffix}"
                else:
                    yield f"{base}/{suffix}"

    @staticmethod
    def _extract_int(text: str) -> str:
        m = re.search(r"\d+", text)
        return m.group(0) if m else ""

    def parse_shops(self, html: str) -> list[Shop]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("div.txt")
        results: list[Shop] = []
        for c in cards:
            a = c.select_one("div.tit a")
            if not a:
                continue
            detail_url = a.get("href", "").strip()
            if detail_url.startswith("//"):
                detail_url = f"https:{detail_url}"
            shop_id = detail_url.rstrip("/").split("/")[-1] if detail_url else ""
            name = a.get("title", "").strip() or a.get_text(strip=True)
            category = " / ".join(x.get_text(strip=True) for x in c.select("span.tag"))
            address = c.select_one("div.tag-addr span.addr")
            address_text = address.get_text(strip=True) if address else ""
            district = "崇州市" if any(k in address_text for k in CHONGZHOU_KEYWORDS) else ""
            score = c.select_one("span.sml-rank-stars")
            score_class = " ".join(score.get("class", [])) if score else ""
            review = c.select_one("a.review-num")
            price = c.select_one("a.mean-price")
            results.append(
                Shop(
                    shop_id=shop_id,
                    name=name,
                    category=category,
                    address=address_text,
                    district=district,
                    score=score_class,
                    review_count=self._extract_int(review.get_text("", strip=True) if review else ""),
                    avg_price=self._extract_int(price.get_text("", strip=True) if price else ""),
                    detail_url=detail_url,
                )
            )
        return [s for s in results if s.district]

    def save_shops(self, shops: list[Shop]) -> None:
        if not shops:
            return
        conn = sqlite3.connect(self.db_path)
        conn.executemany(
            """
            INSERT INTO shops (shop_id, name, category, address, district, score, review_count, avg_price, detail_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(shop_id) DO UPDATE SET
                name=excluded.name,
                category=excluded.category,
                address=excluded.address,
                district=excluded.district,
                score=excluded.score,
                review_count=excluded.review_count,
                avg_price=excluded.avg_price,
                detail_url=excluded.detail_url,
                updated_at=CURRENT_TIMESTAMP
            """,
            [
                (s.shop_id, s.name, s.category, s.address, s.district, s.score, s.review_count, s.avg_price, s.detail_url)
                for s in shops
            ],
        )
        conn.commit()
        conn.close()

    def export_csv(self) -> None:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT shop_id, name, category, address, district, score, review_count, avg_price, detail_url, updated_at FROM shops"
        ).fetchall()
        conn.close()
        with self.output_csv.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["shop_id", "name", "category", "address", "district", "score", "review_count", "avg_price", "detail_url", "updated_at"])
            writer.writerows(rows)

    def run(self) -> None:
        if not self.channel_urls:
            raise ValueError("未配置 CHANNEL_URLS，请先复制 config.example.env 为 .env 并填写。")
        self.init_storage()
        total = 0
        for url in self.iter_listing_urls():
            try:
                html = self.fetch(url)
                shops = self.parse_shops(html)
                self.save_shops(shops)
                total += len(shops)
                print(f"[OK] {url} -> {len(shops)} 条崇州店铺")
            except Exception as e:
                print(f"[ERR] {url} -> {e}")
        self.export_csv()
        print(f"完成。累计入库（含更新）: {total}，CSV: {self.output_csv}")


if __name__ == "__main__":
    DianpingSpider().run()
