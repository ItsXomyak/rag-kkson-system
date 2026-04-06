#!/usr/bin/env python3
"""Scrape scientific articles from KKSON/KOKSNVO-recommended journal sources.

Full coverage of 121 journals from the official KOKSNVO list (Приказ №52, 28.01.2021).
Supports 85+ OJS journals via OAI-PMH and 4 NAN RK journals via HTML scraping.
Non-OJS journals are covered via CyberLeninka fallback.

Sources:
  1. CyberLeninka (OAI-PMH + PDF download) — largest source, covers non-OJS journals
  2. OJS journals (OAI-PMH + free PDFs) — 85+ portals from 30+ institutions
  3. nauka-nanrk.kz NAN RK journals — direct HTML scraping for 4 series

Usage:
    python -m scripts.scrape_articles cyberleninka --limit 100
    python -m scripts.scrape_articles ojs --limit 500
    python -m scripts.scrape_articles nanrk --limit 30
    python -m scripts.scrape_articles all --limit 1000

Downloaded PDFs go to data/pdfs/ by default.
"""

import argparse
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("scraper")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KKSON-RAG-Research/1.0; academic-research)"
}

# Rate limiting: seconds between requests
DELAY = 1.0


# ── CyberLeninka ─────────────────────────────────────────────


def scrape_cyberleninka(output_dir: Path, limit: int) -> int:
    """Harvest Kazakhstan articles from CyberLeninka via OAI-PMH.

    OAI-PMH endpoint: https://cyberleninka.ru/oai
    Set: Kazakhstan
    PDF pattern: https://cyberleninka.ru/article/n/{slug}/pdf
    """
    oai_url = "https://cyberleninka.ru/oai"
    downloaded = 0

    logger.info("CyberLeninka: harvesting Kazakhstan articles via OAI-PMH...")

    params = {
        "verb": "ListRecords",
        "metadataPrefix": "oai_dc",
        "set": "Kazakhstan",
    }

    while downloaded < limit:
        try:
            resp = httpx.get(oai_url, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("OAI-PMH request failed: %s", e)
            break

        soup = BeautifulSoup(resp.text, "xml")
        records = soup.find_all("record")

        if not records:
            logger.info("No more records from CyberLeninka.")
            break

        for record in records:
            if downloaded >= limit:
                break

            # Extract article URL from dc:identifier
            identifiers = record.find_all("dc:identifier")
            article_url = None
            for ident in identifiers:
                text = ident.get_text()
                if "cyberleninka.ru/article/n/" in text:
                    article_url = text
                    break

            if not article_url:
                continue

            # Extract title for filename
            title_el = record.find("dc:title")
            title = title_el.get_text()[:80] if title_el else "untitled"
            safe_title = _safe_filename(title)

            pdf_url = article_url.rstrip("/") + "/pdf"
            pdf_path = output_dir / f"cyberleninka_{safe_title}.pdf"

            if pdf_path.exists():
                logger.debug("Already exists: %s", pdf_path.name)
                downloaded += 1
                continue

            if _download_pdf(pdf_url, pdf_path):
                downloaded += 1
                logger.info(
                    "  [%d/%d] %s", downloaded, limit, pdf_path.name
                )

            time.sleep(DELAY)

        # Check for resumption token
        token_el = soup.find("resumptionToken")
        if token_el and token_el.get_text():
            params = {
                "verb": "ListRecords",
                "resumptionToken": token_el.get_text(),
            }
        else:
            break

    logger.info("CyberLeninka: downloaded %d articles.", downloaded)
    return downloaded


# ── KazNU OJS Journals ───────────────────────────────────────

OJS_JOURNALS = [
    # ══════════════════════════════════════════════════════════
    # КазНУ аль-Фараби (20 журналов)
    # ══════════════════════════════════════════════════════════
    # STEM
    {"name": "kaznu-biology",       "oai": "https://bb.kaznu.kz/index.php/biology/oai",              "base": "https://bb.kaznu.kz"},
    {"name": "kaznu-chemistry",     "oai": "https://bulletin.chemistry.kz/index.php/kaznu/oai",      "base": "https://bulletin.chemistry.kz"},
    {"name": "kaznu-math-mech-cs",  "oai": "https://bm.kaznu.kz/index.php/kaznu/oai",               "base": "https://bm.kaznu.kz"},
    {"name": "kaznu-physics",       "oai": "https://phst.kaznu.kz/index.php/journal/oai",            "base": "https://phst.kaznu.kz"},
    {"name": "kaznu-ecology",       "oai": "https://bulletin-ecology.kaznu.kz/index.php/1-eco/oai",  "base": "https://bulletin-ecology.kaznu.kz"},
    {"name": "kaznu-geography",     "oai": "https://bulletin-geography.kaznu.kz/index.php/1-geo/oai","base": "https://bulletin-geography.kaznu.kz"},
    # Гуманитарные / Социальные
    {"name": "kaznu-history",       "oai": "https://bulletin-history.kaznu.kz/index.php/1-history/oai",    "base": "https://bulletin-history.kaznu.kz"},
    {"name": "kaznu-philosophy",    "oai": "https://bulletin-philospolit.kaznu.kz/index.php/1-pol/oai",    "base": "https://bulletin-philospolit.kaznu.kz"},
    {"name": "kaznu-pedagogy",      "oai": "https://bulletin-pedagogic-sc.kaznu.kz/index.php/ped/oai",     "base": "https://bulletin-pedagogic-sc.kaznu.kz"},
    {"name": "kaznu-psysoc",        "oai": "https://bulletin-psysoc.kaznu.kz/index.php/1-psy/oai",         "base": "https://bulletin-psysoc.kaznu.kz"},
    {"name": "kaznu-philology",     "oai": "https://philart.kaznu.kz/index.php/1-FIL/oai",                 "base": "https://philart.kaznu.kz"},
    {"name": "kaznu-economics",     "oai": "https://be.kaznu.kz/index.php/math/oai",                       "base": "https://be.kaznu.kz"},
    {"name": "kaznu-intl-law",      "oai": "https://bulletin-ir-law.kaznu.kz/index.php/1-mo/oai",          "base": "https://bulletin-ir-law.kaznu.kz"},
    {"name": "kaznu-law",           "oai": "https://bulletin-law.kaznu.kz/index.php/journal/oai",           "base": "https://bulletin-law.kaznu.kz"},
    {"name": "kaznu-oriental",      "oai": "https://bulletin-orientalism.kaznu.kz/index.php/1-vostok/oai", "base": "https://bulletin-orientalism.kaznu.kz"},
    {"name": "kaznu-journalism",    "oai": "https://bulletin-journalism.kaznu.kz/index.php/1-journal/oai", "base": "https://bulletin-journalism.kaznu.kz"},
    {"name": "kaznu-religion",      "oai": "https://bulletin-religion.kaznu.kz/index.php/1-rel/oai",       "base": "https://bulletin-religion.kaznu.kz"},
    # КазНУ — англоязычные международные
    {"name": "kaznu-ijmph",         "oai": "https://ijmph.kaznu.kz/index.php/kaznu/oai",                   "base": "https://ijmph.kaznu.kz"},
    {"name": "kaznu-ijbch",         "oai": "https://ijbch.kaznu.kz/index.php/kaznu/oai",                   "base": "https://ijbch.kaznu.kz"},
    {"name": "kaznu-ect",           "oai": "https://ect-journal.kz/index.php/ectj/oai",                    "base": "https://ect-journal.kz"},

    # ══════════════════════════════════════════════════════════
    # ЕНУ Гумилёва (14 журналов)
    # ══════════════════════════════════════════════════════════
    {"name": "enu-history",         "oai": "https://jhistory.enu.kz/index.php/jHistory/oai",    "base": "https://jhistory.enu.kz"},
    {"name": "enu-hist-phil-rel",   "oai": "https://bulhistphaa.enu.kz/index.php/main/oai",     "base": "https://bulhistphaa.enu.kz"},
    {"name": "enu-philology",       "oai": "https://bulphil.enu.kz/index.php/main/oai",         "base": "https://bulphil.enu.kz"},
    {"name": "enu-ped-psy-soc",     "oai": "https://bulpedps.enu.kz/index.php/main/oai",        "base": "https://bulpedps.enu.kz"},
    {"name": "enu-economics",       "oai": "https://bulecon.enu.kz/index.php/main/oai",          "base": "https://bulecon.enu.kz"},
    {"name": "enu-politics",        "oai": "https://bulpolit.enu.kz/index.php/main/oai",         "base": "https://bulpolit.enu.kz"},
    {"name": "enu-sociology",       "oai": "https://socjournal.enu.kz/index.php/main/oai",       "base": "https://socjournal.enu.kz"},
    {"name": "enu-intl-law",        "oai": "https://eajil.enu.kz/index.php/main/oai",            "base": "https://eajil.enu.kz"},
    {"name": "enu-journalism",      "oai": "https://buljourn.enu.kz/index.php/main/oai",         "base": "https://buljourn.enu.kz"},
    {"name": "enu-biology",         "oai": "https://bulbiol.enu.kz/index.php/main/oai",          "base": "https://bulbiol.enu.kz"},
    {"name": "enu-math-cs",         "oai": "https://bulmathcs.enu.kz/index.php/main/oai",        "base": "https://bulmathcs.enu.kz"},
    {"name": "enu-technical",       "oai": "https://bultech.enu.kz/index.php/main/oai",          "base": "https://bultech.enu.kz"},
    # ЕНУ — англоязычные международные
    {"name": "enu-emj",             "oai": "https://emj.enu.kz/index.php/main/oai",              "base": "https://emj.enu.kz"},
    {"name": "enu-ephys",           "oai": "https://www.ephys.kz/index.php/main/oai",            "base": "https://www.ephys.kz"},

    # ══════════════════════════════════════════════════════════
    # НАН РК — Национальная академия наук (8 журналов)
    # ══════════════════════════════════════════════════════════
    {"name": "nanrk-bio-med",       "oai": "https://journals.nauka-nanrk.kz/biological-medical/oai",     "base": "https://journals.nauka-nanrk.kz/biological-medical"},
    {"name": "nanrk-chem-tech",     "oai": "https://journals.nauka-nanrk.kz/chemistry-technology/oai",   "base": "https://journals.nauka-nanrk.kz/chemistry-technology"},
    {"name": "nanrk-reports",       "oai": "https://journals.nauka-nanrk.kz/reports-science/oai",        "base": "https://journals.nauka-nanrk.kz/reports-science"},
    {"name": "nanrk-bulletin",      "oai": "https://journals.nauka-nanrk.kz/bulletin-science/oai",       "base": "https://journals.nauka-nanrk.kz/bulletin-science"},
    {"name": "nanrk-phys-math",     "oai": "https://journals.nauka-nanrk.kz/physics-mathematics/oai",    "base": "https://journals.nauka-nanrk.kz/physics-mathematics"},
    {"name": "nanrk-social-human",  "oai": "https://journals.nauka-nanrk.kz/social-human/oai",           "base": "https://journals.nauka-nanrk.kz/social-human"},
    {"name": "nanrk-earth-science", "oai": "https://journals.nauka-nanrk.kz/earth-science/oai",          "base": "https://journals.nauka-nanrk.kz/earth-science"},
    {"name": "nanrk-economics",     "oai": "https://journals.nauka-nanrk.kz/economics/oai",              "base": "https://journals.nauka-nanrk.kz/economics"},

    # ══════════════════════════════════════════════════════════
    # Караганда — Букетов (7 серий)
    # ══════════════════════════════════════════════════════════
    {"name": "kgu-pedagogy",        "oai": "https://pedagogy-vestnik.buketov.edu.kz/index.php/pedagogy-vestnik/oai",    "base": "https://pedagogy-vestnik.buketov.edu.kz"},
    {"name": "kgu-law",             "oai": "https://law-vestnik.buketov.edu.kz/index.php/law/oai",                      "base": "https://law-vestnik.buketov.edu.kz"},
    {"name": "kgu-philology",       "oai": "https://philology-vestnik.buketov.edu.kz/index.php/philology-vestnik/oai",  "base": "https://philology-vestnik.buketov.edu.kz"},
    {"name": "kgu-economics",       "oai": "https://bbr.buketov.edu.kz/index.php/economy-vestnik/oai",                  "base": "https://bbr.buketov.edu.kz"},
    {"name": "kgu-history-philo",   "oai": "https://history-philosophy-vestnik.buketov.edu.kz/index.php/main/oai",      "base": "https://history-philosophy-vestnik.buketov.edu.kz"},
    {"name": "kgu-bio-med-geo",     "oai": "https://feb.buketov.edu.kz/index.php/bmg-vestnik/oai",                      "base": "https://feb.buketov.edu.kz"},
    {"name": "kgu-physics",         "oai": "https://physics-vestnik.buketov.edu.kz/index.php/physics/oai",              "base": "https://physics-vestnik.buketov.edu.kz"},

    # ══════════════════════════════════════════════════════════
    # Абай КазНПУ (8 серий)
    # ══════════════════════════════════════════════════════════
    {"name": "kaznpu-pedagogy",     "oai": "https://bulletin-pedagogy.kaznpu.kz/index.php/ped/oai",          "base": "https://bulletin-pedagogy.kaznpu.kz"},
    {"name": "kaznpu-psychology",   "oai": "https://bulletin-psychology.kaznpu.kz/index.php/ped/oai",        "base": "https://bulletin-psychology.kaznpu.kz"},
    {"name": "kaznpu-histsocpol",   "oai": "https://bulletin-histsocpolit.kaznpu.kz/index.php/ped/oai",     "base": "https://bulletin-histsocpolit.kaznpu.kz"},
    {"name": "kaznpu-phmath",       "oai": "https://bulletin-phmath.kaznpu.kz/index.php/ped/oai",            "base": "https://bulletin-phmath.kaznpu.kz"},
    {"name": "kaznpu-philology",    "oai": "https://bulletin-philology.kaznpu.kz/index.php/ped/oai",         "base": "https://bulletin-philology.kaznpu.kz"},
    {"name": "kaznpu-specped",      "oai": "https://bulletin-specped.kaznpu.kz/index.php/ped/oai",           "base": "https://bulletin-specped.kaznpu.kz"},
    {"name": "kaznpu-naturalgeog",  "oai": "https://bulletin-naturalgeog.kaznpu.kz/index.php/ped/oai",       "base": "https://bulletin-naturalgeog.kaznpu.kz"},
    {"name": "kaznpu-pedpsy",       "oai": "https://journal-pedpsy.kaznpu.kz/index.php/ped/oai",             "base": "https://journal-pedpsy.kaznpu.kz"},

    # ══════════════════════════════════════════════════════════
    # Сельское хозяйство / Ветеринария (4 журнала)
    # ══════════════════════════════════════════════════════════
    {"name": "kaznaru-research",    "oai": "https://journal.kaznaru.edu.kz/index.php/research/oai",                   "base": "https://journal.kaznaru.edu.kz"},
    {"name": "kazatu-agriculture",  "oai": "https://bulletinofscience.kazatu.edu.kz/index.php/bulletinofscience/oai",  "base": "https://bulletinofscience.kazatu.edu.kz"},
    {"name": "kazatu-veterinary",   "oai": "https://bulletinofscience.kazatu.edu.kz/index.php/veterinary-science/oai", "base": "https://bulletinofscience.kazatu.edu.kz"},
    {"name": "wkatu-gylym",         "oai": "https://ojs.wkau.kz/index.php/gbj/oai",                                   "base": "https://ojs.wkau.kz"},

    # ══════════════════════════════════════════════════════════
    # Сатпаев Университет (КазНТУ) (1 журнал)
    # ══════════════════════════════════════════════════════════
    {"name": "satbayev-vestnik",    "oai": "https://vestnik.satbayev.university/index.php/journal/oai",  "base": "https://vestnik.satbayev.university"},

    # ══════════════════════════════════════════════════════════
    # Семей медицина университеті (1 журнал)
    # ══════════════════════════════════════════════════════════
    {"name": "semey-medicine",      "oai": "https://newjournal.ssmu.kz/index.php/journalssmu/oai",  "base": "https://newjournal.ssmu.kz"},

    # ══════════════════════════════════════════════════════════
    # Абылай хан ҚазХҚ және ӘТУ (3 серии)
    # ══════════════════════════════════════════════════════════
    {"name": "ablaikhan-irr",       "oai": "https://bulletin-irr.ablaikhan.kz/index.php/j1/oai",          "base": "https://bulletin-irr.ablaikhan.kz"},
    {"name": "ablaikhan-philology", "oai": "https://bulletin-philology.ablaikhan.kz/index.php/j1/oai",    "base": "https://bulletin-philology.ablaikhan.kz"},
    {"name": "ablaikhan-pedagogy",  "oai": "https://bulletin-pedagogical.ablaikhan.kz/index.php/j1/oai",  "base": "https://bulletin-pedagogical.ablaikhan.kz"},

    # ══════════════════════════════════════════════════════════
    # Ахмет Ясауи университеті (2 журнала)
    # ══════════════════════════════════════════════════════════
    {"name": "yassawi-vestnik",     "oai": "https://journals.ayu.edu.kz/index.php/habarshy/oai",     "base": "https://journals.ayu.edu.kz"},
    {"name": "yassawi-philology",   "oai": "https://journals.ayu.edu.kz/index.php/philology/oai",    "base": "https://journals.ayu.edu.kz"},

    # ══════════════════════════════════════════════════════════
    # АУЭС — Алматы энергетика және байланыс (1 журнал)
    # ══════════════════════════════════════════════════════════
    {"name": "aues-vestnik",        "oai": "https://vestnik.aues.kz/index.php/none/oai",  "base": "https://vestnik.aues.kz"},

    # ══════════════════════════════════════════════════════════
    # Astana IT University (1 журнал)
    # ══════════════════════════════════════════════════════════
    {"name": "astanait-journal",    "oai": "https://journal.astanait.edu.kz/index.php/ojs/oai",  "base": "https://journal.astanait.edu.kz"},

    # ══════════════════════════════════════════════════════════
    # Д.Серікбаев ВКТУ (2 журнала)
    # ══════════════════════════════════════════════════════════
    {"name": "ekstu-vestnik",       "oai": "https://journals.ektu.kz/index.php/vestnik/oai",    "base": "https://journals.ektu.kz"},
    {"name": "ekstu-ssadh",         "oai": "https://ojs.ektu.kz/index.php/ssadh/oai",           "base": "https://ojs.ektu.kz"},

    # ══════════════════════════════════════════════════════════
    # Байтұрсынов Қостанай университеті (1 журнал)
    # ══════════════════════════════════════════════════════════
    {"name": "kostanay-3i",         "oai": "https://ojs.ksu.edu.kz/index.php/3i/oai",  "base": "https://ojs.ksu.edu.kz"},

    # ══════════════════════════════════════════════════════════
    # Қоркыт Ата Қызылорда (1 журнал) — OJS
    # ══════════════════════════════════════════════════════════
    {"name": "korkytata-vestnik",   "oai": "https://vestnik.korkyt.edu.kz/index.php/main/oai",  "base": "https://vestnik.korkyt.edu.kz"},

    # ══════════════════════════════════════════════════════════
    # Еуразия гуманитарлық институты (1 журнал)
    # ══════════════════════════════════════════════════════════
    {"name": "egi-bulletin",        "oai": "https://ojs.egi.kz/BULLETIN/oai",  "base": "https://ojs.egi.kz"},

    # ══════════════════════════════════════════════════════════
    # НИИ и Академии — специализированные журналы (14 журналов)
    # ══════════════════════════════════════════════════════════
    # Философия, саясаттану және дінтану институты
    {"name": "alfarabi-philosophy", "oai": "https://alfarabijournal.org/index.php/journal/oai",    "base": "https://alfarabijournal.org"},
    {"name": "adam-alemi",          "oai": "https://adamalemijournal.com/index.php/aa/oai",        "base": "https://adamalemijournal.com"},
    # М.О. Әуезов Әдебиет және өнер институты
    {"name": "keruen-literature",   "oai": "https://keruenjournal.kz/main/oai",                    "base": "https://keruenjournal.kz"},
    # Жүргенов Өнер академиясы
    {"name": "cajas-art",           "oai": "https://cajas.kz/journal/oai",                         "base": "https://cajas.kz"},
    # Металлургия және кең байыту институты
    {"name": "kims-metallurgy",     "oai": "https://kims-imio.com/index.php/main/oai",            "base": "https://kims-imio.com"},
    # Жану проблемалары институты
    {"name": "combustion-plasma",   "oai": "https://cpc-journal.kz/index.php/cpcj/oai",           "base": "https://cpc-journal.kz"},
    # Ұлттық биотехнология орталығы
    {"name": "biotech-eurasian",    "oai": "https://biotechlink.org/index.php/journal/oai",        "base": "https://biotechlink.org"},
    # Ә.Б.Бектуров Химия ғылымдары институты
    {"name": "chemjournal-kz",      "oai": "https://chemjournal.kz/index.php/journal/oai",         "base": "https://chemjournal.kz"},
    # Ш. Уәлиханов Тарих институты
    {"name": "otan-tarikhy",        "oai": "https://otan.history.iie.kz/index.php/main/oai",      "base": "https://otan.history.iie.kz"},
    # Қаз. Онкология және радиология институты
    {"name": "oncology-kz",         "oai": "https://ojs.oncojournal.kz/index.php/main/oai",       "base": "https://ojs.oncojournal.kz"},
    # Репродуктивтік медицина
    {"name": "repromed-kz",         "oai": "https://repromed.kz/index.php/journal/oai",           "base": "https://repromed.kz"},
    # Journal of Health Development (МОЗ РК)
    {"name": "jhd-health",          "oai": "https://jhdkz.org/index.php/jhd/oai",                 "base": "https://jhdkz.org"},
    # Қаз. спорт және туризм академиясы
    {"name": "sport-tmfk",          "oai": "http://46.34.130.122/index.php/tmfk/oai",             "base": "http://46.34.130.122"},
    # Мемлекеттік басқару академиясы (при Президенте РК)
    {"name": "apa-governance",      "oai": "https://journal.apa.kz/index.php/path/oai",           "base": "https://journal.apa.kz"},

    # ══════════════════════════════════════════════════════════
    # КИСЭ / КАЗИСС при Президенте РК (3 журнала)
    # ══════════════════════════════════════════════════════════
    {"name": "kisi-kogam",          "oai": "https://journal-kogam.kisi.kz/index.php/kd/oai",      "base": "https://journal-kogam.kisi.kz"},
    {"name": "kisi-spektr",         "oai": "https://journal-ks.kisi.kz/index.php/ks/oai",         "base": "https://journal-ks.kisi.kz"},
    {"name": "kisi-caa",            "oai": "https://journal-caa.kisi.kz/index.php/caa/oai",       "base": "https://journal-caa.kisi.kz"},

    # ══════════════════════════════════════════════════════════
    # NEICON/Elpub-hosted OJS (URL pattern: /jour/) (9 журналов)
    # ══════════════════════════════════════════════════════════
    {"name": "narxoz-caer",         "oai": "https://caer.narxoz.kz/jour/oai",                     "base": "https://caer.narxoz.kz"},
    {"name": "atu-vestnik",         "oai": "https://www.vestnik-atu.kz/jour/oai",                 "base": "https://www.vestnik-atu.kz"},
    {"name": "turan-vestnik",       "oai": "https://vestnik.turan-edu.kz/jour/oai",               "base": "https://vestnik.turan-edu.kz"},
    {"name": "nnc-vestnik",         "oai": "https://journals.nnc.kz/jour/oai",                    "base": "https://journals.nnc.kz"},
    {"name": "uib-ejebs",           "oai": "https://ejebs.uib.kz/jour/oai",                      "base": "https://ejebs.uib.kz"},
    {"name": "esp-economics",       "oai": "https://esp.ieconom.kz/jour/oai",                     "base": "https://esp.ieconom.kz"},
    {"name": "jpra-agromarket",     "oai": "https://www.jpra-kazniiapk.kz/jour/oai",              "base": "https://www.jpra-kazniiapk.kz"},
    {"name": "keu-vestnik",         "oai": "https://vestnik.kuef.kz/jour/oai",                    "base": "https://vestnik.kuef.kz"},
    {"name": "neft-gaz",            "oai": "https://vestnik-ngo.kz/jour/oai",                     "base": "https://vestnik-ngo.kz"},

    # ══════════════════════════════════════════════════════════
    # Turkic Studies (ЕНУ) (1 журнал)
    # ══════════════════════════════════════════════════════════
    {"name": "enu-turkic",          "oai": "https://tsj.enu.kz/index.php/main/oai",               "base": "https://tsj.enu.kz"},
]

# Non-OJS journals (no OAI-PMH, covered via CyberLeninka or manual download):
# - Торайғыров университеті (10 серий) — custom platform, vestnik.tou.edu.kz
# - ҚарТУ «Труды университета» (4 серии) — custom platform, tu.kstu.kz
# - ҚазҰМУ Асфендияров — custom PHP, vestnik.kaznmu.edu.kz
# - ҚазБСҚА (КазГАСА) — custom platform, vestnik.kazgasa.kz
# - Bilig (Ясауи) — Turkish platform, bilig.yesevi.edu.tr
# - «Қазақстан фармациясы» — WordPress, pharmkaz.kz
# - «Горный журнал Казахстана» — WordPress, minmag.kz
# - edu.e-history.kz — custom platform, SSL expired
# - ҰИА (Нац. инженерная академия) — WordPress, journal.neark.kz
# - DKU CAJWR — WordPress/Scholastica, water-ca.org


def scrape_ojs(output_dir: Path, limit: int) -> int:
    """Harvest articles from all KOKSNVO OJS journals via OAI-PMH."""
    downloaded = 0
    per_journal = max(limit // len(OJS_JOURNALS), 3)

    for journal in OJS_JOURNALS:
        if downloaded >= limit:
            break

        logger.info("OJS [%s]: harvesting via OAI-PMH...", journal["name"])
        journal_count = 0

        params = {
            "verb": "ListRecords",
            "metadataPrefix": "oai_dc",
        }

        while journal_count < per_journal and downloaded < limit:
            try:
                resp = httpx.get(
                    journal["oai"], params=params, headers=HEADERS, timeout=30
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.error(
                    "KazNU [%s] OAI failed: %s", journal["name"], e
                )
                break

            soup = BeautifulSoup(resp.text, "xml")
            records = soup.find_all("record")

            if not records:
                break

            for record in records:
                if journal_count >= per_journal or downloaded >= limit:
                    break

                identifiers = record.find_all("dc:identifier")
                article_url = None
                for ident in identifiers:
                    text = ident.get_text()
                    if "/article/view/" in text:
                        article_url = text
                        break

                if not article_url:
                    continue

                title_el = record.find("dc:title")
                title = title_el.get_text()[:80] if title_el else "untitled"
                safe_title = _safe_filename(title)
                pdf_path = output_dir / f"ojs_{journal['name']}_{safe_title}.pdf"

                if pdf_path.exists():
                    journal_count += 1
                    downloaded += 1
                    continue

                # OJS PDF: try to find galley link from article page
                pdf_url = _find_ojs_pdf(article_url)
                if pdf_url and _download_pdf(pdf_url, pdf_path):
                    journal_count += 1
                    downloaded += 1
                    logger.info(
                        "  [%d/%d] %s", downloaded, limit, pdf_path.name
                    )

                time.sleep(DELAY)

            token_el = soup.find("resumptionToken")
            if token_el and token_el.get_text():
                params = {
                    "verb": "ListRecords",
                    "resumptionToken": token_el.get_text(),
                }
            else:
                break

        logger.info(
            "OJS [%s]: downloaded %d articles.", journal["name"], journal_count
        )

    logger.info("OJS total: downloaded %d articles.", downloaded)
    return downloaded


# ── NAN RK (nauka-nanrk.kz) ─────────────────────────────────

# NAN RK journals for HTML scraping fallback (covers issues not in OAI-PMH)
NANRK_JOURNALS = [
    "https://journals.nauka-nanrk.kz/bulletin-science",
    "https://journals.nauka-nanrk.kz/physics-mathematics",
    "https://journals.nauka-nanrk.kz/social-human",
    "https://journals.nauka-nanrk.kz/earth-science",
]


def scrape_nanrk(output_dir: Path, limit: int) -> int:
    """Scrape articles from NAN RK journal portal."""
    downloaded = 0
    per_journal = max(limit // len(NANRK_JOURNALS), 5)

    for base_url in NANRK_JOURNALS:
        if downloaded >= limit:
            break

        journal_name = base_url.split("/")[-1]
        logger.info("NAN RK [%s]: scraping archive...", journal_name)
        journal_count = 0

        # Try to get the archive page listing issues
        try:
            resp = httpx.get(
                f"{base_url}/issue/archive", headers=HEADERS, timeout=20
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("NAN RK [%s] archive failed: %s", journal_name, e)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find issue links
        issue_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/issue/view/" in href:
                issue_links.append(urljoin(base_url, href))

        for issue_url in issue_links[:3]:  # Latest 3 issues
            if journal_count >= per_journal or downloaded >= limit:
                break

            try:
                resp = httpx.get(issue_url, headers=HEADERS, timeout=20)
                resp.raise_for_status()
            except httpx.HTTPError:
                continue

            issue_soup = BeautifulSoup(resp.text, "html.parser")

            # Collect unique article URLs from the issue page
            seen_urls = set()
            article_links = []
            for a in issue_soup.find_all("a", href=True):
                href = a["href"]
                if "/article/view/" not in href:
                    continue
                full_url = urljoin(base_url, href)
                # Skip galley sub-links (e.g. /view/123/456) — keep only main articles
                if re.search(r"/article/view/\d+$", full_url) and full_url not in seen_urls:
                    seen_urls.add(full_url)
                    title = a.get_text().strip()[:80]
                    article_links.append((full_url, title))

            for article_url, link_title in article_links:
                if journal_count >= per_journal or downloaded >= limit:
                    break

                # Get real title from article page if link text is short
                title, pdf_url = _get_article_title_and_pdf(article_url, link_title)
                safe_title = _safe_filename(title)
                pdf_path = output_dir / f"nanrk_{journal_name}_{safe_title}.pdf"

                if pdf_path.exists():
                    journal_count += 1
                    downloaded += 1
                    continue

                if pdf_url and _download_pdf(pdf_url, pdf_path):
                    journal_count += 1
                    downloaded += 1
                    logger.info(
                        "  [%d/%d] %s", downloaded, limit, pdf_path.name
                    )

                time.sleep(DELAY)

        logger.info(
            "NAN RK [%s]: downloaded %d articles.", journal_name, journal_count
        )

    logger.info("NAN RK total: downloaded %d articles.", downloaded)
    return downloaded


# ── Helpers ──────────────────────────────────────────────────


def _get_article_title_and_pdf(article_url: str, fallback_title: str) -> tuple[str, str | None]:
    """Fetch an OJS article page to get its real title and PDF URL."""
    try:
        resp = httpx.get(article_url, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError:
        return fallback_title or "untitled", None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Get title from <h1> or <meta name="DC.Title">
    title = fallback_title
    meta_title = soup.find("meta", attrs={"name": "DC.Title"})
    if meta_title and meta_title.get("content"):
        title = meta_title["content"][:80]
    elif soup.find("h1"):
        h1_text = soup.find("h1").get_text().strip()
        if len(h1_text) > 10:
            title = h1_text[:80]

    pdf_url = None

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/article/download/" in href:
            pdf_url = urljoin(article_url, href)
            break

    if not pdf_url:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"/article/view/\d+/\d+", href):
                download_url = href.replace("/article/view/", "/article/download/")
                pdf_url = urljoin(article_url, download_url)
                break

    return title, pdf_url


def _find_ojs_pdf(article_url: str) -> str | None:
    """Find the PDF download URL on an OJS article page.

    OJS serves PDF galleys at /article/view/{id}/{galley} (HTML viewer)
    but the actual PDF binary is at /article/download/{id}/{galley}.
    """
    try:
        resp = httpx.get(article_url, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # OJS pattern 1: link with /article/download/
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/article/download/" in href:
            return urljoin(article_url, href)

    # OJS pattern 2: galley link /article/view/{id}/{galley-id} → convert to /download/
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text().strip().lower()
        if "/article/view/" in href and ("pdf" in text or "pdf" in href.lower()):
            download_url = href.replace("/article/view/", "/article/download/")
            return urljoin(article_url, download_url)

    # OJS pattern 3: any galley view link with a numeric sub-path (e.g. /view/30/6)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"/article/view/\d+/\d+", href):
            download_url = href.replace("/article/view/", "/article/download/")
            return urljoin(article_url, download_url)

    return None


def _download_pdf(url: str, path: Path) -> bool:
    """Download a PDF file with error handling."""
    try:
        resp = httpx.get(
            url, headers=HEADERS, timeout=30, follow_redirects=True
        )
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type and not resp.content[:5] == b"%PDF-":
            logger.debug("Not a PDF: %s (content-type: %s)", url, content_type)
            return False

        path.write_bytes(resp.content)
        return True
    except httpx.HTTPError as e:
        logger.debug("Download failed: %s — %s", url, e)
        return False


def _safe_filename(title: str) -> str:
    """Convert a title to a safe filename."""
    safe = re.sub(r"[^\w\s-]", "", title).strip()
    safe = re.sub(r"[\s]+", "_", safe)
    return safe[:100] or "untitled"


# ── Custom scrapers (non-OJS sites) ─────────────────────────


# Торайғыров университеті — 10 серий, custom Laravel platform
TORAIGHYROV_SERIES = [
    "vestnik-pedagogic", "vestnik-pm", "vestnik-fil", "vestnik-energy",
    "vestnik-gum", "vestnik-econ", "vestnik-himbiol", "vestnik-law",
    "vestnik-ntk", "localhistory",
]


def scrape_toraighyrov(output_dir: Path, limit: int) -> int:
    """Scrape Toraighyrov University journals (custom Laravel platform)."""
    downloaded = 0
    per_series = max(limit // len(TORAIGHYROV_SERIES), 3)

    for series in TORAIGHYROV_SERIES:
        if downloaded >= limit:
            break
        base = f"https://{series}.tou.edu.kz"
        logger.info("TOU [%s]: scraping archive...", series)
        series_count = 0

        try:
            resp = httpx.get(f"{base}/archive/journals", headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("TOU [%s] archive failed: %s", series, e)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        # Find issue PDF links (/storage/journals/{ID}.pdf)
        for a in soup.find_all("a", href=True):
            if series_count >= per_series or downloaded >= limit:
                break
            href = a["href"]
            if "/storage/journals/" in href and href.endswith(".pdf"):
                pdf_url = urljoin(base, href)
                title = a.get_text().strip()[:80] or href.split("/")[-1]
                safe = _safe_filename(title)
                pdf_path = output_dir / f"tou_{series}_{safe}.pdf"
                if pdf_path.exists():
                    series_count += 1
                    downloaded += 1
                    continue
                if _download_pdf(pdf_url, pdf_path):
                    series_count += 1
                    downloaded += 1
                    logger.info("  [%d/%d] %s", downloaded, limit, pdf_path.name)
                time.sleep(DELAY)

        # Also try article-level PDFs from /archive/articles
        if series_count < per_series and downloaded < limit:
            try:
                resp = httpx.get(f"{base}/archive/articles", headers=HEADERS, timeout=20)
                resp.raise_for_status()
                asoup = BeautifulSoup(resp.text, "html.parser")
                for a in asoup.find_all("a", href=True):
                    if series_count >= per_series or downloaded >= limit:
                        break
                    href = a["href"]
                    if "/storage/articles/" in href and href.endswith(".pdf"):
                        pdf_url = urljoin(base, href)
                        title = a.get_text().strip()[:80] or "article"
                        safe = _safe_filename(title)
                        pdf_path = output_dir / f"tou_{series}_{safe}.pdf"
                        if pdf_path.exists():
                            series_count += 1
                            downloaded += 1
                            continue
                        if _download_pdf(pdf_url, pdf_path):
                            series_count += 1
                            downloaded += 1
                            logger.info("  [%d/%d] %s", downloaded, limit, pdf_path.name)
                        time.sleep(DELAY)
            except httpx.HTTPError:
                pass

        logger.info("TOU [%s]: downloaded %d.", series, series_count)
    logger.info("TOU total: downloaded %d articles.", downloaded)
    return downloaded


def scrape_kartu(output_dir: Path, limit: int) -> int:
    """Scrape KarTU 'Trudy universiteta' (custom Laravel platform)."""
    downloaded = 0
    base = "https://tu.kstu.kz"
    logger.info("KarTU: scraping archive...")

    try:
        resp = httpx.get(f"{base}/archive", headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("KarTU archive failed: %s", e)
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    # Find issue links
    issue_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/archive/issue/" in href or "/archive/journal/" in href:
            issue_links.append(urljoin(base, href))

    for issue_url in issue_links[:10]:
        if downloaded >= limit:
            break
        try:
            resp = httpx.get(issue_url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except httpx.HTTPError:
            continue

        isoup = BeautifulSoup(resp.text, "html.parser")
        for a in isoup.find_all("a", href=True):
            if downloaded >= limit:
                break
            href = a["href"]
            if "/publication/publication/download/" in href or (
                "/issue/issue/download/" in href
            ):
                pdf_url = urljoin(base, href)
                title = a.get_text().strip()[:80] or "article"
                safe = _safe_filename(title)
                pdf_path = output_dir / f"kartu_{safe}.pdf"
                if pdf_path.exists():
                    downloaded += 1
                    continue
                if _download_pdf(pdf_url, pdf_path):
                    downloaded += 1
                    logger.info("  [%d/%d] %s", downloaded, limit, pdf_path.name)
                time.sleep(DELAY)

    logger.info("KarTU total: downloaded %d articles.", downloaded)
    return downloaded


def scrape_kaznmu(output_dir: Path, limit: int) -> int:
    """Scrape KazNMU Asfendiyarov vestnik (custom PHP)."""
    downloaded = 0
    base = "https://vestnik.kaznmu.edu.kz"
    logger.info("KazNMU: scraping archive...")

    try:
        resp = httpx.get(f"{base}/archive.php", headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("KazNMU archive failed: %s", e)
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    # Find PDF links (direct .pdf links in archive page)
    for a in soup.find_all("a", href=True):
        if downloaded >= limit:
            break
        href = a["href"]
        if href.endswith(".pdf"):
            pdf_url = urljoin(base, href)
            title = a.get_text().strip()[:80] or href.split("/")[-1].replace(".pdf", "")
            safe = _safe_filename(title)
            pdf_path = output_dir / f"kaznmu_{safe}.pdf"
            if pdf_path.exists():
                downloaded += 1
                continue
            if _download_pdf(pdf_url, pdf_path):
                downloaded += 1
                logger.info("  [%d/%d] %s", downloaded, limit, pdf_path.name)
            time.sleep(DELAY)

    logger.info("KazNMU total: downloaded %d articles.", downloaded)
    return downloaded


def scrape_kazgasa(output_dir: Path, limit: int) -> int:
    """Scrape KazGASA vestnik (Yii framework)."""
    downloaded = 0
    base = "https://vestnik.kazgasa.kz"
    logger.info("KazGASA: scraping archive...")

    try:
        resp = httpx.get(f"{base}/site/archive", headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("KazGASA archive failed: %s", e)
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    # Find issue links (archive-number?id=)
    issue_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "archive-number" in href and "id=" in href:
            issue_links.append(urljoin(base, href))

    for issue_url in issue_links[:8]:
        if downloaded >= limit:
            break
        try:
            resp = httpx.get(issue_url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except httpx.HTTPError:
            continue

        isoup = BeautifulSoup(resp.text, "html.parser")
        for a in isoup.find_all("a", href=True):
            if downloaded >= limit:
                break
            href = a["href"]
            if href.endswith(".pdf") and "uploads" in href:
                pdf_url = urljoin(base, href)
                title = a.get_text().strip()[:80] or "article"
                safe = _safe_filename(title)
                pdf_path = output_dir / f"kazgasa_{safe}.pdf"
                if pdf_path.exists():
                    downloaded += 1
                    continue
                if _download_pdf(pdf_url, pdf_path):
                    downloaded += 1
                    logger.info("  [%d/%d] %s", downloaded, limit, pdf_path.name)
                time.sleep(DELAY)

    logger.info("KazGASA total: downloaded %d articles.", downloaded)
    return downloaded


def scrape_bilig(output_dir: Path, limit: int) -> int:
    """Scrape Bilig journal from DergiPark (Turkish academic platform)."""
    downloaded = 0
    base = "https://dergipark.org.tr"
    logger.info("Bilig: scraping DergiPark archive...")

    try:
        resp = httpx.get(
            f"{base}/tr/pub/bilig/archive", headers=HEADERS, timeout=20
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("Bilig archive failed: %s", e)
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    issue_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/pub/bilig/issue/" in href:
            issue_links.append(urljoin(base, href))

    for issue_url in list(dict.fromkeys(issue_links))[:5]:
        if downloaded >= limit:
            break
        try:
            resp = httpx.get(issue_url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except httpx.HTTPError:
            continue

        isoup = BeautifulSoup(resp.text, "html.parser")
        # Find article pages
        article_links = []
        for a in isoup.find_all("a", href=True):
            href = a["href"]
            if "/pub/bilig/article/" in href and href not in article_links:
                article_links.append(urljoin(base, href))

        for art_url in list(dict.fromkeys(article_links)):
            if downloaded >= limit:
                break
            try:
                aresp = httpx.get(art_url, headers=HEADERS, timeout=20)
                aresp.raise_for_status()
            except httpx.HTTPError:
                continue

            art_soup = BeautifulSoup(aresp.text, "html.parser")
            title_tag = art_soup.find("h3", class_="article-title")
            title = title_tag.get_text().strip()[:80] if title_tag else "article"

            # Find PDF download link
            for a in art_soup.find_all("a", href=True):
                href = a["href"]
                if "/download/article-file/" in href:
                    pdf_url = urljoin(base, href)
                    safe = _safe_filename(title)
                    pdf_path = output_dir / f"bilig_{safe}.pdf"
                    if pdf_path.exists():
                        downloaded += 1
                        break
                    if _download_pdf(pdf_url, pdf_path):
                        downloaded += 1
                        logger.info("  [%d/%d] %s", downloaded, limit, pdf_path.name)
                    break
            time.sleep(DELAY)

    logger.info("Bilig total: downloaded %d articles.", downloaded)
    return downloaded


def _scrape_wordpress_journal(
    name: str, archive_url: str, output_dir: Path, limit: int
) -> int:
    """Generic WordPress journal scraper — finds PDF links in archive pages."""
    downloaded = 0
    logger.info("%s: scraping WordPress archive...", name)

    try:
        resp = httpx.get(archive_url, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("%s archive failed: %s", name, e)
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")

    # Collect all internal page links from archive (issue/category pages)
    page_links = set()
    base = archive_url.rsplit("/", 1)[0]
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.endswith(".pdf"):
            page_links.add(("pdf", urljoin(archive_url, href), a.get_text().strip()[:80]))
        elif base in href and href != archive_url:
            page_links.add(("page", urljoin(archive_url, href), ""))

    # Download direct PDFs from archive page
    for kind, url, title in list(page_links):
        if downloaded >= limit:
            break
        if kind == "pdf":
            safe = _safe_filename(title or url.split("/")[-1].replace(".pdf", ""))
            pdf_path = output_dir / f"{name.lower()}_{safe}.pdf"
            if pdf_path.exists():
                downloaded += 1
                continue
            if _download_pdf(url, pdf_path):
                downloaded += 1
                logger.info("  [%d/%d] %s", downloaded, limit, pdf_path.name)
            time.sleep(DELAY)

    # Follow issue/category pages to find more PDFs
    for kind, url, _ in list(page_links)[:20]:
        if downloaded >= limit:
            break
        if kind != "page":
            continue
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError:
            continue
        psoup = BeautifulSoup(resp.text, "html.parser")
        for a in psoup.find_all("a", href=True):
            if downloaded >= limit:
                break
            href = a["href"]
            if href.endswith(".pdf"):
                pdf_url = urljoin(url, href)
                title = a.get_text().strip()[:80] or href.split("/")[-1].replace(".pdf", "")
                safe = _safe_filename(title)
                pdf_path = output_dir / f"{name.lower()}_{safe}.pdf"
                if pdf_path.exists():
                    downloaded += 1
                    continue
                if _download_pdf(pdf_url, pdf_path):
                    downloaded += 1
                    logger.info("  [%d/%d] %s", downloaded, limit, pdf_path.name)
                time.sleep(DELAY)

    logger.info("%s total: downloaded %d articles.", name, downloaded)
    return downloaded


# WordPress-based journals
WORDPRESS_JOURNALS = [
    {"name": "pharmkaz",  "archive": "https://pharmkaz.kz/glavnaya/arxiv-zhurnala-2001-2026-gody/"},
    {"name": "minmag",    "archive": "https://minmag.kz/ru/%D0%BE%D0%B1%D0%BB%D0%BE%D0%B6%D0%BA%D0%B8-%D0%B8-%D1%81%D0%BE%D0%B4%D0%B5%D1%80%D0%B6%D0%B0%D0%BD%D0%B8%D0%B5/"},
    {"name": "neark",     "archive": "https://journal.neark.kz/arhiv/"},
    {"name": "cajwr",     "archive": "https://water-ca.org/issues"},
]


def scrape_wordpress(output_dir: Path, limit: int) -> int:
    """Scrape all WordPress-based KOKSNVO journals."""
    downloaded = 0
    per_journal = max(limit // len(WORDPRESS_JOURNALS), 3)
    for journal in WORDPRESS_JOURNALS:
        if downloaded >= limit:
            break
        remaining = min(per_journal, limit - downloaded)
        downloaded += _scrape_wordpress_journal(
            journal["name"], journal["archive"], output_dir, remaining
        )
    return downloaded


def scrape_ehistory(output_dir: Path, limit: int) -> int:
    """Scrape edu.e-history.kz (try HTTP fallback for expired SSL)."""
    downloaded = 0
    logger.info("e-history: trying to access...")

    for proto in ("https", "http"):
        try:
            resp = httpx.get(
                f"{proto}://edu.e-history.kz",
                headers=HEADERS, timeout=15, follow_redirects=True,
            )
            resp.raise_for_status()
            base = f"{proto}://edu.e-history.kz"
            break
        except httpx.HTTPError:
            continue
    else:
        logger.error("e-history: site unreachable (SSL expired, HTTP failed).")
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a", href=True):
        if downloaded >= limit:
            break
        href = a["href"]
        if href.endswith(".pdf"):
            pdf_url = urljoin(base, href)
            title = a.get_text().strip()[:80] or "article"
            safe = _safe_filename(title)
            pdf_path = output_dir / f"ehistory_{safe}.pdf"
            if pdf_path.exists():
                downloaded += 1
                continue
            if _download_pdf(pdf_url, pdf_path):
                downloaded += 1
                logger.info("  [%d/%d] %s", downloaded, limit, pdf_path.name)
            time.sleep(DELAY)

    logger.info("e-history total: downloaded %d articles.", downloaded)
    return downloaded


def scrape_custom(output_dir: Path, limit: int) -> int:
    """Scrape all non-OJS KOKSNVO journals with custom scrapers."""
    total = 0
    remaining = limit

    scrapers = [
        ("Toraighyrov", scrape_toraighyrov),
        ("KarTU", scrape_kartu),
        ("KazNMU", scrape_kaznmu),
        ("KazGASA", scrape_kazgasa),
        ("Bilig", scrape_bilig),
        ("WordPress", scrape_wordpress),
        ("e-history", scrape_ehistory),
    ]

    for name, func in scrapers:
        if remaining <= 0:
            break
        count = func(output_dir, remaining)
        total += count
        remaining -= count

    return total


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape KKSON/KOKSNVO journal articles as PDFs"
    )
    parser.add_argument(
        "source",
        choices=["cyberleninka", "kaznu", "ojs", "nanrk", "custom", "all"],
        help="Source to scrape (ojs=102 OJS journals, custom=non-OJS sites, all=everything)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max articles to download (default: 50)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/pdfs",
        help="Output directory (default: data/pdfs)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    source = args.source

    logger.info("=" * 60)
    logger.info("KKSON/KOKSNVO Article Scraper — Full Coverage")
    logger.info("Source: %s | Limit: %d | Output: %s", source, args.limit, output_dir)
    logger.info("OJS journals: %d | Custom scrapers: 7 | CyberLeninka: unlimited", len(OJS_JOURNALS))
    logger.info("=" * 60)

    if source in ("cyberleninka", "all"):
        total += scrape_cyberleninka(output_dir, args.limit)

    if source in ("kaznu", "ojs", "all"):
        remaining = args.limit - total if source == "all" else args.limit
        total += scrape_ojs(output_dir, max(remaining, 0))

    if source in ("nanrk", "all"):
        remaining = args.limit - total if source == "all" else args.limit
        total += scrape_nanrk(output_dir, max(remaining, 0))

    if source in ("custom", "all"):
        remaining = args.limit - total if source == "all" else args.limit
        total += scrape_custom(output_dir, max(remaining, 0))

    logger.info("=" * 60)
    logger.info("Total downloaded: %d articles", total)
    logger.info("Next step: python -m scripts.ingest")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
