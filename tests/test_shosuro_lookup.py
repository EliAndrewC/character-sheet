"""Sanity checks for the Shosuro 5th Dan average-bonus lookup table."""

from app.data import shosuro_lowest_3_avg, shosuro_lowest_3_for


def test_table_covers_rolled_3_through_10_for_both_reroll_modes():
    for reroll in (True, False):
        assert set(shosuro_lowest_3_avg[reroll].keys()) == set(range(3, 11))


def test_table_values_are_positive():
    for reroll in (True, False):
        for avg in shosuro_lowest_3_avg[reroll].values():
            assert avg > 0


def test_more_dice_means_lower_avg_bonus():
    """Monotonic decrease: with more dice rolled, the 3 lowest are smaller."""
    for reroll in (True, False):
        prev = float("inf")
        for rolled in range(3, 11):
            cur = shosuro_lowest_3_avg[reroll][rolled]
            assert cur < prev, f"non-monotonic at rolled={rolled} reroll={reroll}"
            prev = cur


def test_reroll_tens_gives_higher_avg():
    """Rerolling 10s raises every die's expected value, so the 3-lowest avg grows."""
    for rolled in range(3, 11):
        with_reroll = shosuro_lowest_3_avg[True][rolled]
        without = shosuro_lowest_3_avg[False][rolled]
        # Rerolling 10s can only help; at 3 dice it helps a lot, at 10 almost none.
        assert with_reroll >= without - 0.1


def test_rolled_3_reroll_bonus_bounded():
    """3 rolled dice -> entire roll is kept; avg is close to avg of 3d10 (reroll 10s)."""
    assert 17.5 <= shosuro_lowest_3_avg[True][3] <= 20
    # No-reroll 3d10: each die avg 5.5, sum 16.5.
    assert 16 <= shosuro_lowest_3_avg[False][3] <= 17


def test_rolled_10_bonus_bounded():
    """Bottom 3 of 10 dice should average roughly 6-8."""
    for reroll in (True, False):
        assert 6 <= shosuro_lowest_3_avg[reroll][10] <= 8


def test_lookup_helper_clamps_out_of_range():
    assert shosuro_lowest_3_for(2, True) == shosuro_lowest_3_avg[True][3]
    assert shosuro_lowest_3_for(15, True) == shosuro_lowest_3_avg[True][10]
    assert shosuro_lowest_3_for(5, False) == shosuro_lowest_3_avg[False][5]


def test_lookup_helper_accepts_boolish():
    assert shosuro_lowest_3_for(5, 1) == shosuro_lowest_3_for(5, True)
    assert shosuro_lowest_3_for(5, 0) == shosuro_lowest_3_for(5, False)
