"""When a share is shown as a rate (owner decision D7). Pure: no database, no I/O.

Below MIN_RATE_N in the denominator one result swings a rate by five points or more, so a
caller sends the counts ("1 of 3") and no rate.
"""

MIN_RATE_N = 20
