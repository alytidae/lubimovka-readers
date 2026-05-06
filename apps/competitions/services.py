import gspread
import re
from apps.plays.models import Play


def _normalize_row_keys(row):
    return {key.strip(): value for key, value in row.items()}


def sync_plays_from_google_sheet(competition):
    if not competition.google_sheet_url:
        return 0

    gc = gspread.service_account(filename="/run/secrets/google_credentials.json")

    sh = gc.open_by_url(competition.google_sheet_url)
    worksheet = sh.get_worksheet(0)
    data = worksheet.get_all_records()

    synced_count = 0

    for row in data:
        row = _normalize_row_keys(row)

        email = row.get(competition.play_author_email_sheet_column_name)
        if not email:
            continue

        title = row.get(competition.play_title_sheet_column_name, "")
        url = row.get(competition.play_url_sheet_column_name, "")
        first_name = row.get(competition.play_author_first_name_sheet_column_name, "")
        last_name = row.get(competition.play_author_last_name_sheet_column_name, "")

        year_raw = row.get(competition.play_author_year_of_birth_sheet_column_name, "")
        year_str = re.split(r"[. /]", str(year_raw))[-1]
        try:
            year = int(year_str)
        except (ValueError, TypeError):
            year = None

        Play.objects.update_or_create(
            competition=competition,
            author_email=email,
            title=title,
            defaults={
                "url": url,
                "author_first_name": first_name,
                "author_last_name": last_name,
                "author_year_of_birth": year,
            },
        )
        synced_count += 1

    return synced_count
