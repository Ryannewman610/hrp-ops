
=== Crypto_King ===
Total TRs: 244
Tables: 106
  TR 0: 7 cells: ['w=10||sup=[]', 'w=50||sup=[]', 'w=6||sup=[]', 'w=314|Horse Racing Game|sup=[]', 'w=360|Wednesday, 3/11/2026 8:15\xa0ET|sup=[]', 'w=10||sup=[]', 'w=10||sup=[]']
  TR 1: 4 cells: ['w=0||sup=[]', 'w=510||sup=[]', 'w=230|Ire Iron StablesPlatinum+Balance:\xa0211.01\xa0\xa0[0.00](34-3-0-4\xa0\xa0$31.41)2026:\xa0(34-3-0-4\xa0\xa0$31.41)Toggle:|sup=[]', 'w=0||sup=[]']
  TR 2: 1 cells: ['w=?||sup=[]']
  TR 3: 1 cells: ['w=?|Ire Iron StablesPlatinum+Balance:\xa0211.01\xa0\xa0[0.00](34-3-0-4\xa0\xa0$31.41)2026:\xa0(34-3-0-4\xa0\xa0$31.41)Toggle:|sup=[]']
  TR 4: 1 cells: ['w=?|Ire Iron StablesPlatinum+|sup=[]']
Work date rows: 106

=== Captain_Cook ===
Total TRs: 234
Tables: 101
  TR 0: 7 cells: ['w=10||sup=[]', 'w=50||sup=[]', 'w=6||sup=[]', 'w=314|Horse Racing Game|sup=[]', 'w=360|Wednesday, 3/11/2026 8:13\xa0ET|sup=[]', 'w=10||sup=[]', 'w=10||sup=[]']
  TR 1: 4 cells: ['w=0||sup=[]', 'w=510||sup=[]', 'w=230|Ire Iron StablesPlatinum+Balance:\xa0211.01\xa0\xa0[0.00](34-3-0-4\xa0\xa0$31.41)2026:\xa0(34-3-0-4\xa0\xa0$31.41)Toggle:|sup=[]', 'w=0||sup=[]']
  TR 2: 1 cells: ['w=?||sup=[]']
  TR 3: 1 cells: ['w=?|Ire Iron StablesPlatinum+Balance:\xa0211.01\xa0\xa0[0.00](34-3-0-4\xa0\xa0$31.41)2026:\xa0(34-3-0-4\xa0\xa0$31.41)Toggle:|sup=[]']
  TR 4: 1 cells: ['w=?|Ire Iron StablesPlatinum+|sup=[]']
Work date rows: 96

=== Cayuga_Lake ===
Total TRs: 253
Tables: 110
  TR 0: 7 cells: ['w=10||sup=[]', 'w=50||sup=[]', 'w=6||sup=[]', 'w=314|Horse Racing Game|sup=[]', 'w=360|Wednesday, 3/11/2026 8:13\xa0ET|sup=[]', 'w=10||sup=[]', 'w=10||sup=[]']
  TR 1: 4 cells: ['w=0||sup=[]', 'w=510||sup=[]', 'w=230|Ire Iron StablesPlatinum+Balance:\xa0211.01\xa0\xa0[0.00](34-3-0-4\xa0\xa0$31.41)2026:\xa0(34-3-0-4\xa0\xa0$31.41)Toggle:|sup=[]', 'w=0||sup=[]']
  TR 2: 1 cells: ['w=?||sup=[]']
  TR 3: 1 cells: ['w=?|Ire Iron StablesPlatinum+Balance:\xa0211.01\xa0\xa0[0.00](34-3-0-4\xa0\xa0$31.41)2026:\xa0(34-3-0-4\xa0\xa0$31.41)Toggle:|sup=[]']
  TR 4: 1 cells: ['w=?|Ire Iron StablesPlatinum+|sup=[]']
Work date rows: 114

=== Checking 04_parse_and_fill.py works parsing ===
Work-related functions/parsing: 6
  def extract_name(profile_s, works_s, meters_s) -> str:
  def parse_works(horse_id: str, horse_name: str, s: Optional[BeautifulSoup], source: str, warnings: L
  warnings.append(f"{horse_id}: no parsed works rows.")
  def join_works_meters(works: List[Dict[str, str]], meters: List[Dict[str, str]], warnings: List[str]
  works = parse_works(horse_id, horse_name, ws, "works_all.html", warnings)
  ap.add_argument("--dry-run", action="store_true", help="Parse only, do not modify workbook")