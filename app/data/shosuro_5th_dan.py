"""Shosuro Actor 5th Dan: average sum of the 3 lowest dice of ``rolled`` dice.

Generated via Monte Carlo (200k trials per cell, seed=1337). Keyed by
``reroll_tens`` (bool) and the number of ``rolled`` dice (3..10 - Shosuro
never keeps fewer than 2, and because the 3 lowest of N dice don't depend
on the kept count, only ``rolled`` matters). Use values <3 and >10 are
clamped to the nearest valid cell by the caller.
"""

shosuro_lowest_3_avg = {
    True: {
        3: 18.3275,
        4: 13.743,
        5: 11.5673,
        6: 10.1164,
        7: 9.0577,
        8: 8.2383,
        9: 7.5745,
        10: 7.0226,
    },
    False: {
        3: 16.5238,
        4: 13.541,
        5: 11.544,
        6: 10.1086,
        7: 9.055,
        8: 8.2485,
        9: 7.5803,
        10: 7.0412,
    },
}
