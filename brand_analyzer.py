"""
brand_analyzer.py
──────────────────
Mengekstrak DNA visual & identitas merek dari website dan Twitter project.

Apa yang dianalisis:
- Palet warna dominan dari CSS, inline styles, meta theme
- Tipografi & spacing cues dari stylesheet
- Tone of voice dari copy website (formal/casual/technical/bold)
- Visual language: apakah geometric? organic? minimal? dense?
- Kata-kata kunci merek yang sering muncul (brand vocabulary)
- Suasana dan nuansa: futuristic? trustworthy? rebellious? institutional?
- Emoji & simbol yang dipakai di Twitter
- Format tweet yang khas (thread? short punchy? data-heavy?)
"""

import re
import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Optional
from collections import Counter

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}


class BrandAnalyzer:
    """
    Menganalisis identitas visual dan brand DNA sebuah project
    dari website dan data Twitter-nya.
    """

    # ─────────────────────────────────────────────────────────────
    # CSS COLOR EXTRACTION
    # ─────────────────────────────────────────────────────────────
    HEX_RE    = re.compile(r'#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b')
    RGB_RE    = re.compile(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)')
    HSL_RE    = re.compile(r'hsla?\(\s*(\d+)\s*,\s*(\d+)%?\s*,\s*(\d+)%?')
    VAR_RE    = re.compile(r'--[\w-]+:\s*(#[0-9A-Fa-f]{3,6}|rgba?\([^)]+\))')

    # Common UI / near-white / near-black yang tidak representatif
    IGNORE_COLORS = {
        "ffffff","fff","000000","000","f0f0f0","f5f5f5","fafafa",
        "eeeeee","eee","cccccc","ccc","aaaaaa","aaa","333333","333",
        "111111","222222","444444","555555","666666","777777","888888",
        "999999","dddddd","ddd","e5e5e5","e0e0e0",
    }

    # ─────────────────────────────────────────────────────────────
    # VIBES / ARCHETYPE MAPPING
    # ─────────────────────────────────────────────────────────────
    VIBE_SIGNALS = {
        "futuristic":   ["future","next-gen","ai","intelligent","automated","protocol","machine","neural","quantum","compute"],
        "rebellious":   ["decentralized","trustless","permissionless","censorship","freedom","sovereign","unstoppable","resist","unbank"],
        "institutional":["secure","compliant","regulated","institutional","enterprise","audit","governance","legal","custody"],
        "community":    ["community","together","dao","vote","member","collective","squad","family","people","social"],
        "minimalist":   ["simple","clean","easy","fast","instant","one-click","seamless","smooth","frictionless"],
        "technical":    ["protocol","algorithm","cryptographic","zkp","layer","consensus","merkle","signature","hash","proof"],
        "bold":         ["first","leading","biggest","most","only","pioneer","original","revolutionary","new standard"],
        "playful":      ["fun","game","earn","reward","play","adventure","explore","discover","magic","delight"],
    }

    COLOR_VIBES = {
        # Hue ranges → vibe
        "electric_blue":  (200, 240),  # futuristic, tech
        "purple":         (270, 310),  # premium, mysterious, DeFi
        "green":          (100, 160),  # growth, DeFi, eco
        "orange_amber":   (25,  50),   # energy, bold, warmth
        "red":            (0,   20),   # bold, urgent, aggressive
        "cyan_teal":      (170, 200),  # clean, modern, web3
        "gold_yellow":    (40,  65),   # premium, value, crypto
        "dark_navy":      None,        # institutional, serious
        "neutral_gray":   None,        # minimal, clean
    }

    def __init__(self):
        self.timeout = aiohttp.ClientTimeout(total=15)

    # ─────────────────────────────────────────────────────────────
    # MAIN ENTRY
    # ─────────────────────────────────────────────────────────────
    async def analyze(self, url: str, html: str,
                      twitter_data: Optional[dict] = None) -> dict:
        """
        Analisis brand DNA lengkap.
        Returns structured brand profile.
        """
        brand = {
            "colors": [],
            "primary_color": "",
            "color_mood": "",
            "vibes": [],
            "dominant_vibe": "",
            "brand_vocabulary": [],
            "tone": "",
            "visual_language": "",
            "twitter_style": {},
            "project_archetype": "",
            "writing_persona": "",
            "thread_angle": "",
            "hook_style": "",
            "emoji_palette": [],
        }

        soup = BeautifulSoup(html, "html.parser")

        # 1. Colors
        colors = self._extract_colors(soup, html)
        brand["colors"] = colors[:8]
        brand["primary_color"] = colors[0] if colors else ""
        brand["color_mood"] = self._color_mood(colors)

        # 2. Vibes dari copy
        all_text = soup.get_text(" ", strip=True).lower()
        vibes = self._detect_vibes(all_text)
        brand["vibes"] = vibes
        brand["dominant_vibe"] = vibes[0] if vibes else "technical"

        # 3. Brand vocabulary
        brand["brand_vocabulary"] = self._extract_brand_vocab(soup)

        # 4. Tone of voice
        brand["tone"] = self._detect_tone(soup)

        # 5. Visual language
        brand["visual_language"] = self._detect_visual_language(soup, html)

        # 6. Twitter style analysis
        if twitter_data and twitter_data.get("success"):
            brand["twitter_style"] = self._analyze_twitter_style(twitter_data)
            brand["emoji_palette"] = brand["twitter_style"].get("emojis", [])

        # 7. Synthesize archetype + writing persona
        brand["project_archetype"] = self._synthesize_archetype(brand)
        brand["writing_persona"]   = self._build_writing_persona(brand)
        brand["thread_angle"]      = self._suggest_thread_angle(brand, all_text)
        brand["hook_style"]        = self._suggest_hook_style(brand)

        return brand

    # ─────────────────────────────────────────────────────────────
    # COLOR EXTRACTION
    # ─────────────────────────────────────────────────────────────
    def _extract_colors(self, soup: BeautifulSoup, html: str) -> list[str]:
        found: Counter = Counter()

        # 1. CSS custom properties (--primary-color, --brand-color, etc.)
        for m in self.VAR_RE.finditer(html):
            val = m.group(1).strip()
            c = self._normalize_color(val)
            if c: found[c] += 10  # high weight for CSS vars

        # 2. Meta theme-color
        tc = soup.find("meta", attrs={"name": "theme-color"})
        if tc and tc.get("content"):
            c = self._normalize_color(tc["content"])
            if c: found[c] += 15

        # 3. Inline styles on prominent elements
        for tag in soup.find_all(True, style=True):
            style = tag.get("style", "")
            for m in self.HEX_RE.finditer(style):
                c = self._normalize_color(m.group(0))
                if c: found[c] += 2

        # 4. SVG fill/stroke
        for svg_el in soup.find_all(["circle","rect","path","polygon","ellipse"]):
            for attr in ["fill","stroke"]:
                val = svg_el.get(attr,"")
                c = self._normalize_color(val)
                if c: found[c] += 3

        # 5. Embedded <style> blocks
        for style_tag in soup.find_all("style"):
            css = style_tag.string or ""
            for m in self.HEX_RE.finditer(css):
                c = self._normalize_color(m.group(0))
                if c: found[c] += 1

        # Sort by frequency, exclude too-common UI colors
        return [c for c, _ in found.most_common(20)
                if c.replace("#","").lower() not in self.IGNORE_COLORS][:8]

    def _normalize_color(self, val: str) -> str:
        val = val.strip()
        if not val or val in ("none","transparent","inherit","currentColor","initial"):
            return ""
        # Already hex
        m = self.HEX_RE.match(val)
        if m:
            h = m.group(1)
            if len(h) == 3:
                h = ''.join(c*2 for c in h)
            return f"#{h.upper()}"
        # RGB
        m = self.RGB_RE.match(val)
        if m:
            r,g,b = int(m.group(1)), int(m.group(2)), int(m.group(3))
            # Skip near-white and near-black
            if r > 240 and g > 240 and b > 240: return ""
            if r < 20  and g < 20  and b < 20:  return ""
            return f"#{r:02X}{g:02X}{b:02X}"
        return ""

    def _color_mood(self, colors: list[str]) -> str:
        if not colors:
            return "neutral"
        primary = colors[0].lstrip("#")
        try:
            r = int(primary[0:2], 16)
            g = int(primary[2:4], 16)
            b = int(primary[4:6], 16)
        except Exception:
            return "neutral"

        # Convert to HSL-ish hue
        r_, g_, b_ = r/255, g/255, b/255
        cmax = max(r_, g_, b_)
        cmin = min(r_, g_, b_)
        delta = cmax - cmin
        if delta < 0.05:
            return "monochrome"

        if cmax == r_:
            hue = 60 * (((g_ - b_) / delta) % 6)
        elif cmax == g_:
            hue = 60 * ((b_ - r_) / delta + 2)
        else:
            hue = 60 * ((r_ - g_) / delta + 4)

        sat = 0 if (cmax + cmin) == 2 else delta / (1 - abs(cmax + cmin - 1))
        light = (cmax + cmin) / 2

        if sat < 0.15:
            return "monochrome"
        if 200 <= hue <= 260:
            return "electric" if sat > 0.7 else "cool"
        if 270 <= hue <= 310:
            return "premium_purple"
        if 100 <= hue <= 160:
            return "fresh_green"
        if 40 <= hue <= 65:
            return "golden"
        if 0 <= hue <= 20 or hue >= 340:
            return "bold_red"
        if 170 <= hue <= 200:
            return "cyan_modern"
        if 20 <= hue <= 40:
            return "energetic_orange"
        return "vibrant"

    # ─────────────────────────────────────────────────────────────
    # VIBE DETECTION
    # ─────────────────────────────────────────────────────────────
    def _detect_vibes(self, text: str) -> list[str]:
        scores: dict[str, int] = {}
        for vibe, keywords in self.VIBE_SIGNALS.items():
            count = sum(text.count(kw) for kw in keywords)
            if count > 0:
                scores[vibe] = count
        return sorted(scores, key=scores.get, reverse=True)[:4]

    # ─────────────────────────────────────────────────────────────
    # BRAND VOCABULARY
    # ─────────────────────────────────────────────────────────────
    def _extract_brand_vocab(self, soup: BeautifulSoup) -> list[str]:
        """Kata-kata unik yang sering muncul di copy utama — ini adalah bahasa merek."""
        stop = {
            "the","a","an","is","are","was","were","be","been","have","has",
            "do","does","did","will","would","could","should","may","might",
            "to","of","in","for","on","with","at","by","from","and","or","but",
            "not","this","that","these","those","we","our","you","your","they",
            "it","its","all","more","can","get","new","just","about","use",
            "any","how","what","who","when","where","which","also","into","over",
            "your","out","up","if","as","so","than","then","now","only","well",
        }
        text = ""
        # Focus on headings and hero copy — these are brand-intentional
        for el in soup.find_all(["h1","h2","h3","strong","b"]):
            text += " " + el.get_text(" ", strip=True)

        words = re.findall(r'\b[A-Za-z][a-z]{3,}\b', text)
        freq = Counter(w.lower() for w in words if w.lower() not in stop)
        return [w for w, _ in freq.most_common(15)]

    # ─────────────────────────────────────────────────────────────
    # TONE DETECTION
    # ─────────────────────────────────────────────────────────────
    def _detect_tone(self, soup: BeautifulSoup) -> str:
        hero = ""
        for el in soup.find_all(["h1","h2","p"])[:10]:
            hero += " " + el.get_text(" ", strip=True)
        hero = hero.lower()

        exclamations = hero.count("!")
        questions    = hero.count("?")
        avg_sentence = len(hero.split(".")) / max(len(hero.split()), 1)
        has_we       = "we " in hero or "our " in hero
        has_you      = "you " in hero or "your " in hero

        if exclamations > 3:
            return "bold_energetic"
        if has_you and not has_we:
            return "user_centric"
        if has_we and not has_you:
            return "builder_voice"
        if "trustless" in hero or "permissionless" in hero or "protocol" in hero:
            return "technical_authoritative"
        if questions > 2:
            return "conversational_curious"
        return "professional_clear"

    # ─────────────────────────────────────────────────────────────
    # VISUAL LANGUAGE
    # ─────────────────────────────────────────────────────────────
    def _detect_visual_language(self, soup: BeautifulSoup, html: str) -> str:
        html_lower = html.lower()
        css_combined = " ".join(s.string or "" for s in soup.find_all("style")).lower()

        has_gradient  = "gradient" in css_combined or "gradient" in html_lower
        has_blur      = "blur" in css_combined or "backdrop" in css_combined
        has_animation = "animation" in css_combined or "keyframe" in css_combined
        has_grid      = "grid" in css_combined
        svg_count     = len(soup.find_all("svg"))
        img_count     = len(soup.find_all("img"))

        if has_gradient and has_blur and has_animation:
            return "glassmorphism_dynamic"
        if has_gradient and svg_count > 5:
            return "gradient_illustrated"
        if not has_gradient and not has_animation:
            return "flat_minimal"
        if has_animation and not has_gradient:
            return "motion_focused"
        if svg_count > img_count * 2:
            return "vector_geometric"
        if img_count > 10:
            return "photo_rich"
        return "clean_modern"

    # ─────────────────────────────────────────────────────────────
    # TWITTER STYLE ANALYSIS
    # ─────────────────────────────────────────────────────────────
    def _analyze_twitter_style(self, twitter_data: dict) -> dict:
        tweets = twitter_data.get("recent_tweets", [])
        if not tweets:
            return {}

        all_text = " ".join(tweets)

        # Emoji extraction
        emoji_re = re.compile(
            "[\U0001F300-\U0001F9FF"
            "\U00002600-\U000027BF"
            "\U0001FA00-\U0001FA6F"
            "\U0001FA70-\U0001FAFF]+",
            flags=re.UNICODE
        )
        all_emojis = emoji_re.findall(all_text)
        emoji_freq = Counter(all_emojis)
        top_emojis = [e for e, _ in emoji_freq.most_common(8)]

        # Avg tweet length
        lengths = [len(t) for t in tweets]
        avg_len = sum(lengths) / len(lengths) if lengths else 0

        # Has numbers/data?
        has_numbers = bool(re.search(r'\d+[KkMmBb%]?\b', all_text))

        # Hashtag usage
        hashtags = re.findall(r'#\w+', all_text)

        # Tone from tweets
        exclamation_rate = all_text.count("!") / max(len(tweets), 1)
        question_rate    = all_text.count("?") / max(len(tweets), 1)

        if exclamation_rate > 1.5:
            tweet_tone = "high_energy"
        elif question_rate > 1:
            tweet_tone = "engaging_curious"
        elif has_numbers:
            tweet_tone = "data_driven"
        elif avg_len < 100:
            tweet_tone = "punchy_brief"
        else:
            tweet_tone = "narrative_detailed"

        # Posting topics
        announcements = twitter_data.get("announcements", [])

        return {
            "emojis": top_emojis,
            "avg_tweet_length": round(avg_len),
            "tweet_tone": tweet_tone,
            "uses_data": has_numbers,
            "top_hashtags": hashtags[:5],
            "announcement_count": len(announcements),
            "key_topics": twitter_data.get("key_topics", []),
            "followers": twitter_data.get("profile", {}).get("followers", ""),
        }

    # ─────────────────────────────────────────────────────────────
    # SYNTHESIS
    # ─────────────────────────────────────────────────────────────
    def _synthesize_archetype(self, brand: dict) -> str:
        """Menentukan satu archetpe merek dari semua sinyal."""
        vibe      = brand.get("dominant_vibe", "technical")
        mood      = brand.get("color_mood", "neutral")
        tone      = brand.get("tone", "professional_clear")
        tw_tone   = brand.get("twitter_style", {}).get("tweet_tone", "")

        # Matrix sederhana
        if vibe == "rebellious":
            return "the_rebel"          # DeFi murni, anti-establishment
        if vibe == "institutional" and mood in ("electric","cool"):
            return "the_institution"    # Serius, compliant, besar
        if vibe == "community" and tw_tone in ("high_energy","engaging_curious"):
            return "the_movement"       # Membangun gerakan sosial
        if vibe == "futuristic" and mood in ("electric","premium_purple"):
            return "the_frontier"       # Tech-first, masa depan
        if vibe == "playful":
            return "the_playground"     # Gaming, NFT, fun
        if vibe == "minimalist" and tone in ("user_centric","professional_clear"):
            return "the_tool"           # Fokus utility, bukan visi
        if vibe == "bold":
            return "the_challenger"     # Menantang status quo
        return "the_builder"            # Default: tim yang serius membangun

    def _build_writing_persona(self, brand: dict) -> str:
        """
        Membangun persona penulis yang sesuai dengan brand — ini yang diinject ke prompt.
        Bukan instruksi teknis, tapi karakter manusia yang akan menulis thread ini.
        """
        archetype = brand.get("project_archetype", "the_builder")
        vibes     = brand.get("vibes", [])
        vocab     = brand.get("brand_vocabulary", [])[:6]
        tw_style  = brand.get("twitter_style", {})
        emojis    = brand.get("emoji_palette", [])[:4]

        persona_map = {
            "the_rebel": (
                "Kamu adalah seorang analis yang pernah lelah dengan sistem keuangan lama. "
                "Kamu menulis dengan urgensi — seperti seseorang yang tahu sesuatu yang belum banyak orang sadari. "
                "Kalimatmu pendek karena kamu tidak punya waktu untuk basa-basi. "
                "Skeptis terhadap klaim besar, tapi genuinely excited ketika sebuah proyek benar-benar beda."
            ),
            "the_institution": (
                "Kamu adalah analis berpengalaman yang terbiasa membaca prospektus dan whitepaper. "
                "Tulisanmu presisi. Kamu tidak over-claim — kamu under-promise dan over-deliver dalam konten. "
                "Credibility adalah segalanya. Setiap poin punya backing-nya."
            ),
            "the_movement": (
                "Kamu adalah seseorang yang genuinely percaya bahwa teknologi bisa mengubah power dinamics. "
                "Kamu menulis seperti sedang berbicara ke seseorang yang belum tahu kenapa ini penting — "
                "bukan menggurui, tapi mengajak. Energimu tulus, bukan hype."
            ),
            "the_frontier": (
                "Kamu adalah tech writer yang hidup di garis terdepan inovasi. "
                "Kamu excited bukan karena hype, tapi karena kamu benar-benar paham teknologinya. "
                "Kamu bisa menjelaskan hal kompleks dengan analogi yang tepat — tidak menyederhanakan, tapi membuat accessible."
            ),
            "the_playground": (
                "Kamu adalah seseorang yang tahu bahwa fun dan serious bisa berjalan beriringan. "
                "Tulisanmu ringan tapi ada substance-nya. Kamu tidak takut bercanda, "
                "tapi kamu juga tahu kapan harus serius tentang mekanisme dan tokenomics."
            ),
            "the_tool": (
                "Kamu adalah power user yang menulis untuk power user lain. "
                "Kamu tidak buang waktu dengan intro panjang — langsung ke apa yang penting. "
                "Kamu respect pembacamu cukup untuk tidak over-explain."
            ),
            "the_challenger": (
                "Kamu adalah seseorang yang frustrasi dengan cara lama — dan akhirnya menemukan sesuatu yang benar-benar menantangnya. "
                "Kamu nulis dengan conviction. Bukan arogan, tapi confident karena kamu sudah cek faktanya."
            ),
            "the_builder": (
                "Kamu adalah seorang yang menghargai craftsmanship. "
                "Kamu tertarik pada bagaimana sesuatu dibangun, bukan hanya apa yang dibangun. "
                "Tulisanmu menunjukkan bahwa kamu benar-benar spent time mempelajari ini — "
                "dan kamu ingin orang lain mendapat 'aha moment' yang sama."
            ),
        }

        base = persona_map.get(archetype, persona_map["the_builder"])

        extras = []
        if vocab:
            extras.append(f"Kamu familiar dengan bahasa merek proyek ini: {', '.join(vocab[:5])}. "
                         f"Gunakan vocabulary ini secara natural — bukan copy-paste, tapi terinternalisasi.")
        if emojis:
            extras.append(f"Project ini sendiri di Twitter sering pakai {' '.join(emojis[:3])} — "
                         f"ini sinyal visual identity mereka. Kamu boleh pakai 1-2 dari ini jika natural.")
        if tw_style.get("uses_data"):
            extras.append("Proyek ini communication style-nya data-driven. Jika ada angka di riset, gunakan.")
        if tw_style.get("tweet_tone") == "high_energy":
            extras.append("Timeline Twitter mereka high-energy. Thread-mu boleh match energy itu — bukan lebay, tapi tidak flat.")

        return base + ("\n\n" + " ".join(extras) if extras else "")

    def _suggest_thread_angle(self, brand: dict, text: str) -> str:
        """Menyarankan sudut pandang unik untuk thread berdasarkan brand."""
        archetype = brand.get("project_archetype", "the_builder")
        vibes     = brand.get("vibes", [])

        angle_map = {
            "the_rebel":      "Mulai dari pertanyaan: 'Siapa yang sebenarnya diuntungkan oleh sistem lama?' — lalu tunjukkan bagaimana proyek ini membalik struktur itu.",
            "the_institution":"Mulai dari gap antara ekspektasi institusi dan realita DeFi saat ini — proyek ini menjawab gap itu dengan cara yang terstruktur.",
            "the_movement":   "Mulai dari momen ketika seorang individu biasa menghadapi barrier yang tidak seharusnya ada — proyek ini ada untuk menghilangkan barrier itu.",
            "the_frontier":   "Mulai dari satu masalah teknis yang belum terpecahkan — lalu tunjukkan bagaimana proyek ini mendekatinya secara engineering.",
            "the_playground": "Mulai dari pengalaman — bukan konsep abstrak, tapi 'bayangkan kamu bisa...' — lalu bongkar teknologi di baliknya.",
            "the_tool":       "Mulai dari workflow yang terputus atau ineffisien yang orang rasakan tiap hari — proyek ini adalah shortcut yang mereka cari.",
            "the_challenger": "Mulai dari satu asumsi umum yang semua orang pegang tentang industri ini — lalu tunjukkan kenapa asumsi itu salah.",
            "the_builder":    "Mulai dari keputusan desain yang paling counter-intuitive dari proyek ini — kenapa tim memilih jalan yang lebih susah?",
        }
        return angle_map.get(archetype, angle_map["the_builder"])

    def _suggest_hook_style(self, brand: dict) -> str:
        """Gaya kalimat pembuka yang cocok dengan brand personality."""
        archetype = brand.get("project_archetype", "the_builder")

        hook_map = {
            "the_rebel":      "Pertanyaan retorika yang menyerang asumsi: 'Kapan terakhir kali kamu benar-benar kontrol asetmu sendiri?'",
            "the_institution":"Statistik atau fakta yang mengejutkan tentang skala masalah yang diselesaikan.",
            "the_movement":   "Cerita satu orang — satu situasi nyata yang bisa dirasakan siapa pun.",
            "the_frontier":   "Paradoks teknis: 'Masalahnya bukan kurangnya data. Masalahnya adalah tidak ada yang bisa memverifikasi data itu.'",
            "the_playground": "Hook yang playful tapi ada punch-nya: buka dengan sesuatu yang unexpected.",
            "the_tool":       "Langsung ke rasa sakit: 'Kalau kamu pernah...' lalu sebutkan friction yang spesifik.",
            "the_challenger": "Bold statement yang bikin orang berhenti scroll: sesuatu yang kebanyakan orang tidak setuju tapi kamu siap argue.",
            "the_builder":    "Mulai dari observasi yang tampak kecil tapi ternyata membuka pemahaman besar.",
        }
        return hook_map.get(archetype, hook_map["the_builder"])

    # ─────────────────────────────────────────────────────────────
    # FORMATTER: jadikan brand profile sebagai teks untuk prompt
    # ─────────────────────────────────────────────────────────────
    def format_for_prompt(self, brand: dict) -> str:
        lines = ["━━━ BRAND DNA ANALYSIS ━━━"]

        if brand.get("colors"):
            lines.append(f"Primary Colors: {', '.join(brand['colors'][:5])}")
        if brand.get("color_mood"):
            lines.append(f"Color Mood: {brand['color_mood']}")
        if brand.get("vibes"):
            lines.append(f"Brand Vibes: {', '.join(brand['vibes'])}")
        if brand.get("brand_vocabulary"):
            lines.append(f"Brand Vocabulary: {', '.join(brand['brand_vocabulary'][:8])}")
        if brand.get("tone"):
            lines.append(f"Website Tone: {brand['tone']}")
        if brand.get("visual_language"):
            lines.append(f"Visual Language: {brand['visual_language']}")

        tw = brand.get("twitter_style", {})
        if tw:
            lines.append(f"\nTwitter Style:")
            if tw.get("emojis"):
                lines.append(f"  Emoji Palette: {' '.join(tw['emojis'][:5])}")
            if tw.get("tweet_tone"):
                lines.append(f"  Tweet Tone: {tw['tweet_tone']}")
            if tw.get("avg_tweet_length"):
                lines.append(f"  Avg Tweet Length: {tw['avg_tweet_length']} chars")
            if tw.get("key_topics"):
                lines.append(f"  Key Topics: {', '.join(tw['key_topics'][:6])}")
            if tw.get("followers"):
                lines.append(f"  Followers: {tw['followers']}")

        lines.append(f"\nProject Archetype: {brand.get('project_archetype','the_builder').replace('_',' ').upper()}")
        lines.append(f"\nSuggested Thread Angle:\n{brand.get('thread_angle','')}")
        lines.append(f"\nSuggested Hook Style:\n{brand.get('hook_style','')}")

        return "\n".join(lines)
