"""보스별 권장 전투력 (인게임 배치 순서·커뮤니티 기준). 전투력 단위: 정수."""
from typing import Any

# 출처: 메이플스토리 보스 전투력 표 (커뮤니티 정리, 2025년 기준)
# https://loat.tistory.com/entry/메이플스토리보스-전투력-표-전체-보스
# 전투력은 절대 지표가 아니며 직업·세팅에 따라 다를 수 있음. 참고용.
BOSS_SPECS: list[dict[str, Any]] = [
    {"name": "자쿰 (EASY)", "min_combat_power": 3_000},
    {"name": "자쿰 (NORMAL)", "min_combat_power": 20_000},
    {"name": "파풀라투스 (EASY)", "min_combat_power": 300_000},
    {"name": "매그너스 (EASY)", "min_combat_power": 150_000},
    {"name": "힐라 (NORMAL)", "min_combat_power": 150_000},
    {"name": "혼테일 (EASY)", "min_combat_power": 120_000},
    {"name": "피에르 (NORMAL)", "min_combat_power": 100_000},
    {"name": "반반 (NORMAL)", "min_combat_power": 100_000},
    {"name": "블러디퀸 (NORMAL)", "min_combat_power": 100_000},
    {"name": "벨룸 (NORMAL)", "min_combat_power": 150_000},
    {"name": "혼테일 (NORMAL)", "min_combat_power": 150_000},
    {"name": "반 레온 (EASY)", "min_combat_power": 300_000},
    {"name": "아카이럼 (EASY)", "min_combat_power": 150_000},
    {"name": "카웅 (NORMAL)", "min_combat_power": 400_000},
    {"name": "혼테일 (CHAOS)", "min_combat_power": 400_000},
    {"name": "핑크빈 (NORMAL)", "min_combat_power": 400_000},
    {"name": "반 레온 (NORMAL)", "min_combat_power": 100_000},
    {"name": "반 레온 (HARD)", "min_combat_power": 300_000},
    {"name": "아카이럼 (NORMAL)", "min_combat_power": 300_000},
    {"name": "매그너스 (NORMAL)", "min_combat_power": 400_000},
    {"name": "파풀라투스 (NORMAL)", "min_combat_power": 1_500_000},
    {"name": "시그너스 (EASY)", "min_combat_power": 400_000},
    {"name": "힐라 (HARD)", "min_combat_power": 800_000},
    {"name": "핑크빈 (CHAOS)", "min_combat_power": 1_600_000},
    {"name": "시그너스 (NORMAL)", "min_combat_power": 600_000},
    {"name": "자쿰 (CHAOS)", "min_combat_power": 900_000},
    {"name": "피에르 (CHAOS)", "min_combat_power": 3_000_000},
    {"name": "반반 (CHAOS)", "min_combat_power": 3_000_000},
    {"name": "블러디퀸 (CHAOS)", "min_combat_power": 3_000_000},
    {"name": "벨룸 (CHAOS)", "min_combat_power": 5_000_000},
    {"name": "매그너스 (HARD)", "min_combat_power": 3_000_000},
    {"name": "파풀라투스 (CHAOS)", "min_combat_power": 6_000_000},
    {"name": "스우 (NORMAL)", "min_combat_power": 7_000_000},
    {"name": "데미안 (NORMAL)", "min_combat_power": 8_000_000},
    {"name": "루시드 (EASY)", "min_combat_power": 12_000_000},
    {"name": "윌 (EASY)", "min_combat_power": 12_000_000},
    {"name": "가디언 엔젤 슬라임 (NORMAL)", "min_combat_power": 8_000_000},
    {"name": "루시드 (NORMAL)", "min_combat_power": 20_000_000},
    {"name": "윌 (NORMAL)", "min_combat_power": 25_000_000},
    {"name": "더스크 (NORMAL)", "min_combat_power": 16_000_000},
    {"name": "듄켈 (NORMAL)", "min_combat_power": 18_000_000},
    {"name": "데미안 (HARD)", "min_combat_power": 20_000_000},
    {"name": "스우 (HARD)", "min_combat_power": 19_000_000},
    {"name": "루시드 (HARD)", "min_combat_power": 40_000_000},
    {"name": "윌 (HARD)", "min_combat_power": 40_000_000},
    {"name": "진 힐라 (NORMAL)", "min_combat_power": 30_000_000},
    {"name": "더스크 (CHAOS)", "min_combat_power": 40_000_000},
    {"name": "듄켈 (HARD)", "min_combat_power": 40_000_000},
    {"name": "진 힐라 (HARD)", "min_combat_power": 50_000_000},
    {"name": "세렌 (NORMAL)", "min_combat_power": 80_000_000},
    {"name": "검은 마법사 (HARD)", "min_combat_power": 120_000_000},
    {"name": "감시자 칼로스 (EASY)", "min_combat_power": 120_000_000},
    {"name": "선택받은 세렌 (HARD)", "min_combat_power": 180_000_000},
    {"name": "최초의 대적자 (EASY)", "min_combat_power": 90_000_000},
    {"name": "카링 (EASY)", "min_combat_power": 250_000_000},
    {"name": "감시자 칼로스 (NORMAL)", "min_combat_power": 250_000_000},
    {"name": "최초의 대적자 (NORMAL)", "min_combat_power": 300_000_000},
    {"name": "스우 (EXTREME)", "min_combat_power": 340_000_000},
    {"name": "카링 (NORMAL)", "min_combat_power": 600_000_000},
    {"name": "림보 (NORMAL)", "min_combat_power": 700_000_000},
    {"name": "감시자 칼로스 (CHAOS)", "min_combat_power": 700_000_000},
    {"name": "발드릭스 (NORMAL)", "min_combat_power": 800_000_000},
    {"name": "카링 (HARD)", "min_combat_power": 1_000_000_000},
    {"name": "최초의 대적자 (HARD)", "min_combat_power": 1_200_000_000},
    {"name": "검은 마법사 (EXTREME)", "min_combat_power": 800_000_000},
    {"name": "선택받은 세렌 (EXTREME)", "min_combat_power": 1_100_000_000},
    {"name": "림보 (HARD)", "min_combat_power": 1_400_000_000},
    {"name": "감시자 칼로스 (EXTREME)", "min_combat_power": 1_600_000_000},
    {"name": "발드릭스 (HARD)", "min_combat_power": 1_700_000_000},
    {"name": "최초의 대적자 (EXTREME)", "min_combat_power": 3_000_000_000},
    {"name": "카링 (EXTREME)", "min_combat_power": 2_500_000_000},
]

# 전투력 1억 이상 구간 안내 문구에 사용
COMBAT_POWER_100M = 100_000_000


def get_doable_bosses(combat_power: int | None) -> tuple[list[str], list[str], list[str]]:
    """전투력 기준 도전 가능 / 도전해볼 만 / 다음 목표 보스 분류."""
    if combat_power is None or combat_power < 0:
        return [], [], []
    doable: list[str] = []
    try_soon: list[str] = []
    next_goal: list[str] = []
    for spec in BOSS_SPECS:
        min_power = int(spec.get("min_combat_power", 0))
        name = spec.get("name", "")
        if not name:
            continue
        if combat_power >= min_power * 1.15:
            doable.append(name)
        elif combat_power >= min_power:
            try_soon.append(name)
        else:
            if len(next_goal) < 5:
                next_goal.append(name)
    return doable, try_soon, next_goal
