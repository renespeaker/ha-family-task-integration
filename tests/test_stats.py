"""Week, month and streak counting, without Home Assistant."""

from datetime import date

from custom_components.family_tasks.ledger import Booking
from custom_components.family_tasks.stats import person_stats

TODAY = date(2026, 10, 14)  # a Wednesday


def award(day: date, points: int = 10, person: str = "Lina") -> tuple[date, Booking]:
    return day, Booking("award", person, points, "task", day.isoformat(), f"k{day}{points}")


def test_counts_this_week_from_monday_and_this_month_from_the_first():
    rows = [
        award(date(2026, 10, 12)),  # Monday this week
        award(date(2026, 10, 11)),  # Sunday last week, same month
        award(date(2026, 9, 30)),  # last month
    ]
    st = person_stats(rows, "Lina", TODAY)
    assert (st.week_points, st.week_tasks) == (10, 1)
    assert (st.month_points, st.month_tasks) == (20, 2)


def test_adjustments_count_as_points_but_not_tasks_and_rewards_not_at_all():
    rows = [
        award(TODAY),
        (TODAY, Booking("adjust", "Lina", 5, "bonus", "x")),
        (TODAY, Booking("redeem", "Lina", 30, "ice", "x")),
    ]
    st = person_stats(rows, "Lina", TODAY)
    assert (st.week_points, st.week_tasks) == (15, 1)


def test_other_people_do_not_count():
    st = person_stats([award(TODAY, person="Ben")], "Lina", TODAY)
    assert (st.week_points, st.streak) == (0, 0)


def test_a_streak_runs_up_to_today():
    rows = [award(date(2026, 10, d)) for d in (11, 12, 13, 14)]
    assert person_stats(rows, "Lina", TODAY).streak == 4


def test_a_streak_still_counts_before_todays_task_is_done():
    rows = [award(date(2026, 10, d)) for d in (12, 13)]
    assert person_stats(rows, "Lina", TODAY).streak == 2


def test_a_missed_day_ends_the_streak_but_not_the_best():
    rows = [award(date(2026, 10, d)) for d in (1, 2, 3, 4, 5, 12)]
    st = person_stats(rows, "Lina", TODAY)
    assert (st.streak, st.best_streak) == (0, 5)


def test_several_tasks_on_one_day_are_one_streak_day():
    rows = [award(TODAY, 10), award(TODAY, 20), award(date(2026, 10, 13))]
    st = person_stats(rows, "Lina", TODAY)
    assert (st.streak, st.week_tasks, st.week_points) == (2, 3, 40)


def test_a_streak_across_the_month_end():
    rows = [award(date(2026, 9, 30)), award(date(2026, 10, 1)), award(date(2026, 10, 2))]
    assert person_stats(rows, "Lina", date(2026, 10, 2)).streak == 3


def test_points_handed_over_for_a_chore_are_no_work():
    rows = [
        award(TODAY, 5),
        (TODAY, Booking("transfer", "Lina", 10, "🔁 Bins", "x")),
        (TODAY, Booking("transfer", "Lina", -4, "🔁 Dishes", "x")),
    ]
    st = person_stats(rows, "Lina", TODAY)
    assert (st.week_points, st.month_points, st.week_tasks) == (5, 5, 1)
