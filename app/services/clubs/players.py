from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Type

from app.services.base import TransfermarktBase
from app.utils.regex import REGEX_DOB
from app.utils.utils import extract_from_url, safe_regex, trim
from app.utils.xpath import Clubs

# Headers indicating national team page (EN/DE).
NATIONAL_TEAM_HEADERS = (
    "International matches",
    "Debut",
    "Länderspiele",  # DE
    "Debüt",  # DE
)


@dataclass
class TransfermarktClubPlayers(TransfermarktBase):
    """
    A class for retrieving and parsing the players of a football club or national team from Transfermarkt.

    Args:
        club_id (str): The unique identifier of the football club or national team.
        season_id (str): The unique identifier of the season.
        URL (str): The URL template for the club's players page on Transfermarkt.
    """

    club_id: Optional[str] = None  # Required in practice; default for dataclass + Python 3.8
    season_id: Optional[str] = None
    URL: str = "https://www.transfermarkt.com/-/kader/verein/{club_id}/saison_id/{season_id}/plus/1"
    past: bool = field(default=False, init=False)
    national: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Initialize the TransfermarktClubPlayers class."""
        self.URL = self.URL.format(club_id=self.club_id, season_id=self.season_id)
        self.page = self.request_url_page()
        self.raise_exception_if_not_found(xpath=Clubs.Players.CLUB_NAME)
        self._update_season_id()
        self._update_page_type_flags()

    def _update_season_id(self) -> None:
        """Update the season ID if not provided by extracting it from the website."""
        if self.season_id is None:
            self.season_id = extract_from_url(
                self.get_text_by_xpath(Clubs.Players.CLUB_URL), "season_id"
            )

    def _update_page_type_flags(self) -> None:
        """Detect if page is past season and if it is a national team (not club)."""
        thead_texts = self.get_list_by_xpath(Clubs.Players.PAST_FLAG) or []
        self.past = "Current club" in thead_texts
        self.national = any(h in thead_texts for h in NATIONAL_TEAM_HEADERS)
        if not self.national:
            # National teams have no Nat. column (flags), only Club.
            has_nat_column = bool(self.page.xpath(Clubs.Players.PAGE_NATIONALITIES))
            if not has_nat_column:
                self.national = True

    def _get_layout(self) -> Type:
        """Return the XPath layout class for current/past club or national team."""
        if self.national:
            return Clubs.Players.National
        return Clubs.Players.Past if self.past else Clubs.Players.Present

    def _parse_national_players(self) -> list[dict]:
        """Parse national team squad from table.items (does not rely on div#yw1)."""
        nt = Clubs.Players.NationalTable
        rows = self.page.xpath(nt.ROWS)
        country_name = (self.get_text_by_xpath(Clubs.Players.CLUB_NAME) or "").strip()
        result = []
        for row in rows:
            player = self._parse_national_row(row, nt, country_name)
            if player:
                result.append(player)
        return result

    def _parse_national_row(self, row: Any, nt: Type, country_name: str) -> Optional[dict]:
        """Extract one player dict from a national team table row, or None if invalid."""
        hrefs = row.xpath(nt.PLAYER_HREF)
        if not hrefs:
            return None
        player_id = extract_from_url(hrefs[0])
        if not player_id:
            return None
        names = row.xpath(nt.PLAYER_NAME)
        name = trim(names[0]) if names else ""
        positions = row.xpath(nt.POSITION)
        position = trim(positions[0]) if positions else ""
        dob_age_text = " ".join(row.xpath(nt.DOB_AGE_CELL))
        dob = safe_regex(dob_age_text, REGEX_DOB, "dob")
        age = safe_regex(dob_age_text, REGEX_DOB, "age")
        club_titles = row.xpath(nt.CLUB_IMG_TITLE)
        current_club = trim(club_titles[0]) if club_titles else None
        heights = row.xpath(nt.HEIGHT)
        height = trim(heights[0]) if heights else ""
        foots = row.xpath(nt.FOOT)
        foot = trim(foots[0]) if foots else ""
        debuts = row.xpath(nt.DEBUT)
        joined_on = trim(debuts[0]) if debuts else ""
        market_elems = row.xpath(nt.MARKET_VALUE)
        market_value = trim(market_elems[0]) if market_elems else ""
        return {
            "id": player_id,
            "name": name,
            "position": position,
            "dateOfBirth": dob or "",
            "age": age or "",
            "nationality": [country_name],
            "currentClub": current_club,
            "height": height,
            "foot": foot,
            "joinedOn": joined_on,
            "joined": "",
            "signedFrom": "",
            "contract": None,
            "marketValue": market_value,
            "status": "",
        }

    def _parse_club_players(self) -> list[dict]:
        """
        Parse player information from the webpage and return a list of dictionaries, each representing a player.

        Returns:
            list[dict]: A list of player information dictionaries.
        """
        layout = self._get_layout()
        page_players_infos = self.page.xpath(Clubs.Players.PAGE_INFOS)
        page_players_signed_from = self.page.xpath(layout.PAGE_SIGNED_FROM)
        page_players_joined_on = self.page.xpath(layout.PAGE_JOINED_ON)

        players_ids = [extract_from_url(url) for url in self.get_list_by_xpath(Clubs.Players.URLS)]
        players_names = self.get_list_by_xpath(Clubs.Players.NAMES)
        players_positions = self.get_list_by_xpath(Clubs.Players.POSITIONS)
        players_dobs = [
            safe_regex(dob_age, REGEX_DOB, "dob") for dob_age in self.get_list_by_xpath(Clubs.Players.DOB_AGE)
        ]
        players_ages = [
            safe_regex(dob_age, REGEX_DOB, "age") for dob_age in self.get_list_by_xpath(Clubs.Players.DOB_AGE)
        ]

        if self.national:
            country_name = (self.get_text_by_xpath(Clubs.Players.CLUB_NAME) or "").strip()
            players_nationalities = [[country_name]] * len(players_ids)
            players_current_club = self.get_list_by_xpath(layout.CURRENT_CLUB)
        else:
            page_nationalities = self.page.xpath(Clubs.Players.PAGE_NATIONALITIES)
            players_nationalities = [
                nat.xpath(Clubs.Players.NATIONALITIES) for nat in page_nationalities
            ]
            players_current_club = (
                self.get_list_by_xpath(Clubs.Players.Past.CURRENT_CLUB)
                if self.past
                else [None] * len(players_ids)
            )

        players_heights = self.get_list_by_xpath(layout.HEIGHTS)
        players_foots = self.get_list_by_xpath(layout.FOOTS, remove_empty=False)
        players_joined_on = ["; ".join(e.xpath(Clubs.Players.JOINED_ON)) for e in page_players_joined_on]
        players_joined = ["; ".join(e.xpath(Clubs.Players.JOINED)) for e in page_players_infos]
        players_signed_from = ["; ".join(e.xpath(Clubs.Players.SIGNED_FROM)) for e in page_players_signed_from]
        players_contracts = (
            [None] * len(players_ids)
            if (self.past or self.national)
            else self.get_list_by_xpath(Clubs.Players.Present.CONTRACTS)
        )
        players_marketvalues = self.get_list_by_xpath(Clubs.Players.MARKET_VALUES)
        players_statuses = [
            "; ".join(e.xpath(Clubs.Players.STATUSES)) for e in page_players_infos if e is not None
        ]

        return [
            {
                "id": idx,
                "name": name,
                "position": position,
                "dateOfBirth": dob,
                "age": age,
                "nationality": nationality,
                "currentClub": current_club,
                "height": height,
                "foot": foot,
                "joinedOn": joined_on,
                "joined": joined,
                "signedFrom": signed_from,
                "contract": contract,
                "marketValue": market_value,
                "status": status,
            }
            for idx, name, position, dob, age, nationality, current_club, height, foot, joined_on, joined, signed_from, contract, market_value, status, in zip(  # noqa: E501
                players_ids,
                players_names,
                players_positions,
                players_dobs,
                players_ages,
                players_nationalities,
                players_current_club,
                players_heights,
                players_foots,
                players_joined_on,
                players_joined,
                players_signed_from,
                players_contracts,
                players_marketvalues,
                players_statuses,
            )
        ]

    def get_club_players(self) -> dict:
        """
        Retrieve and parse player information for the specified football club or national team.

        Returns:
            dict: A dictionary containing the club/team id, player list, and last updated timestamp.
        """
        self.response["id"] = self.club_id
        if self.national:
            self.response["players"] = self._parse_national_players()
        else:
            self.response["players"] = self._parse_club_players()

        return self.response
