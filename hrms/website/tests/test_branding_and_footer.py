"""The HRMS lockup and the footer that sits under every page.

The shell came from a bought admin template, and its footer shipped with
the template vendor's own links -- a ThemeForest licence, "More Themes",
their documentation and their support desk. None of that belongs in an
HRMS, and it is the kind of thing that creeps back in when the base
template is next updated from upstream, so it is pinned here.

Run with: python manage.py test website.tests.test_branding_and_footer
"""
import os
import re

from django.conf import settings as dj_settings
from django.test import TestCase

BRANDING = ("hrms-logo.svg", "hrms-logo-white.svg",
            "hrms-icon.svg", "hrms-icon-white.svg")

# The domains, not the names: base2.html's own comment says what used to be
# there, and that note is worth keeping.
VENDOR_LINKS = ("pixinvent.com", "themeforest.net", "envato.market",
                "ticksy.com", "demos.pixinvent")


class BrandingAssetsTest(TestCase):
    def path(self, name):
        return os.path.join(str(dj_settings.BASE_DIR), "static", "assets",
                            "img", "branding", name)

    def drawing(self, name):
        """The file minus its XML comments -- the note in the white files
        names the colour they replaced, and that is not a fill."""
        with open(self.path(name), encoding="utf-8") as handle:
            return re.sub(r"<!--.*?-->", "", handle.read(), flags=re.S)

    def test_all_four_logo_files_ship(self):
        for name in BRANDING:
            with self.subTest(asset=name):
                self.assertTrue(os.path.exists(self.path(name)), self.path(name))

    def test_the_white_variants_carry_no_brand_colour_left(self):
        """The navy half of the lockup is invisible on a dark shell, which
        is the whole reason the white files exist."""
        for name in ("hrms-logo-white.svg", "hrms-icon-white.svg"):
            with self.subTest(asset=name):
                drawing = self.drawing(name)
                self.assertNotIn("182659", drawing)
                self.assertNotIn("0588F6", drawing)
                self.assertIn("#FFFFFF", drawing)

    def test_the_colour_variants_keep_both_brand_colours(self):
        for name in ("hrms-logo.svg", "hrms-icon.svg"):
            with self.subTest(asset=name):
                drawing = self.drawing(name)
                self.assertIn("#182659", drawing)
                self.assertIn("#0588F6", drawing)


class ShellBrandingTest(TestCase):
    def template(self, rel):
        for directory in dj_settings.TEMPLATES[0]["DIRS"]:
            candidate = os.path.join(str(directory), *rel.split("/"))
            if os.path.exists(candidate):
                with open(candidate, encoding="utf-8") as handle:
                    return handle.read()
        self.fail(f"{rel} not found in TEMPLATES DIRS")

    def test_both_shells_show_the_lockup_in_both_variants(self):
        for rel in ("base2.html", "auth/login.html"):
            with self.subTest(template=rel):
                source = self.template(rel)
                self.assertIn("branding/hrms-logo.svg", source)
                self.assertIn("branding/hrms-logo-white.svg", source)
                self.assertIn("app-logo-colour", source)
                self.assertIn("app-logo-white", source)

    def test_both_shells_use_the_mark_as_the_favicon(self):
        for rel in ("base2.html", "auth/login.html"):
            with self.subTest(template=rel):
                source = self.template(rel)
                self.assertIn('type="image/svg+xml"', source)
                self.assertIn("branding/hrms-icon.svg", source)

    def test_the_footer_names_who_built_it_and_links_only_there(self):
        source = self.template("base2.html")
        footer = source.split("<footer", 1)[1].split("</footer>", 1)[0]
        self.assertIn("zacoinfotech.com", footer)
        self.assertIn("Powered by", footer)
        self.assertIn("Zaco Information Technology", footer)
        self.assertIn('{% now "Y" %}', footer,
                      "the year should come from the server, not document.write")

    def test_the_company_is_spelled_Zaco_everywhere_it_appears(self):
        """It has been written ZAC and ZACO in different places. The name is
        Zaco -- the lockup sets it in capitals, but that is typography, not
        the spelling, so prose in the templates uses Zaco."""
        allowed = {"Zaco", "zacoinfotech"}
        for rel in ("base2.html", "auth/login.html"):
            with self.subTest(template=rel):
                found = re.findall(r"[Zz][Aa][Cc]\w*", self.template(rel))
                stray = sorted({word for word in found if word not in allowed})
                self.assertEqual(stray, [], f"{rel} also spells it {stray}")

    def test_no_template_still_carries_the_vendor_theme_links(self):
        for rel in ("base2.html", "auth/login.html"):
            source = self.template(rel).lower()
            for vendor in VENDOR_LINKS:
                with self.subTest(template=rel, vendor=vendor):
                    self.assertNotIn(vendor, source)
