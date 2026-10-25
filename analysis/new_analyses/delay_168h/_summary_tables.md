### Level values (primary: minimum 1 eligible event)

| calendar | delay (h) | decay origin | stations | station-years | events | mean event abs. rel. error | median over stations |
|---|---|---|---|---|---|---|---|
| deadline_only | 6 | arrival | 9 | 9 | 138 | 0.1654 | 0.1620 |
| deadline_only | 6 | collection | 9 | 9 | 138 | 0.1682 | 0.1630 |
| deadline_only | 24 | arrival | 9 | 9 | 138 | 0.1941 | 0.1951 |
| deadline_only | 24 | collection | 9 | 9 | 138 | 0.2034 | 0.1945 |
| deadline_only | 72 | arrival | 9 | 9 | 138 | 0.2277 | 0.1831 |
| deadline_only | 72 | collection | 9 | 9 | 138 | 0.2335 | 0.1997 |
| deadline_only | 168 | arrival | 9 | 9 | 138 | 0.2707 | 0.1592 |
| deadline_only | 168 | collection | 9 | 9 | 138 | 0.2769 | 0.2521 |
| flow_trigger | 6 | arrival | 9 | 9 | 138 | 0.1442 | 0.1343 |
| flow_trigger | 6 | collection | 9 | 9 | 138 | 0.1465 | 0.1363 |
| flow_trigger | 24 | arrival | 9 | 9 | 138 | 0.1770 | 0.1373 |
| flow_trigger | 24 | collection | 9 | 9 | 138 | 0.1838 | 0.1442 |
| flow_trigger | 72 | arrival | 9 | 9 | 138 | 0.2309 | 0.2028 |
| flow_trigger | 72 | collection | 9 | 9 | 138 | 0.2332 | 0.2036 |
| flow_trigger | 168 | arrival | 9 | 9 | 138 | 0.2872 | 0.2507 |
| flow_trigger | 168 | collection | 9 | 9 | 138 | 0.2801 | 0.2472 |
| uniform | 6 | arrival | 9 | 9 | 138 | 0.1880 | 0.1219 |
| uniform | 6 | collection | 9 | 9 | 138 | 0.1893 | 0.1239 |
| uniform | 24 | arrival | 9 | 9 | 138 | 0.2068 | 0.1462 |
| uniform | 24 | collection | 9 | 9 | 138 | 0.2081 | 0.1532 |
| uniform | 72 | arrival | 9 | 9 | 138 | 0.2481 | 0.2102 |
| uniform | 72 | collection | 9 | 9 | 138 | 0.2413 | 0.1960 |
| uniform | 168 | arrival | 9 | 9 | 138 | 0.2663 | 0.2413 |
| uniform | 168 | collection | 9 | 9 | 138 | 0.2720 | 0.2524 |

### Paired station-bootstrap contrasts (primary)

| factor | calendar | stratum | baseline | candidate | stations | mean difference | 95% station CI | stations favouring candidate |
|---|---|---|---|---|---|---|---|---|
| delay | deadline_only | origin=arrival | deadline_only|delay=72|origin=arrival | deadline_only|delay=6|origin=arrival | 9 | +0.0623 | [+0.0103, +0.1196] | 7.0/9 |
| delay | deadline_only | origin=arrival | deadline_only|delay=72|origin=arrival | deadline_only|delay=24|origin=arrival | 9 | +0.0336 | [-0.0023, +0.0681] | 7.0/9 |
| delay | deadline_only | origin=arrival | deadline_only|delay=24|origin=arrival | deadline_only|delay=6|origin=arrival | 9 | +0.0287 | [+0.0040, +0.0615] | 7.0/9 |
| delay | deadline_only | origin=collection | deadline_only|delay=72|origin=collection | deadline_only|delay=6|origin=collection | 9 | +0.0653 | [+0.0138, +0.1220] | 7.0/9 |
| delay | deadline_only | origin=collection | deadline_only|delay=72|origin=collection | deadline_only|delay=24|origin=collection | 9 | +0.0301 | [-0.0012, +0.0635] | 6.0/9 |
| delay | deadline_only | origin=collection | deadline_only|delay=24|origin=collection | deadline_only|delay=6|origin=collection | 9 | +0.0352 | [+0.0111, +0.0668] | 8.0/9 |
| delay | flow_trigger | origin=arrival | flow_trigger|delay=72|origin=arrival | flow_trigger|delay=6|origin=arrival | 9 | +0.0867 | [+0.0515, +0.1272] | 9.0/9 |
| delay | flow_trigger | origin=arrival | flow_trigger|delay=72|origin=arrival | flow_trigger|delay=24|origin=arrival | 9 | +0.0539 | [+0.0296, +0.0770] | 8.0/9 |
| delay | flow_trigger | origin=arrival | flow_trigger|delay=24|origin=arrival | flow_trigger|delay=6|origin=arrival | 9 | +0.0328 | [+0.0027, +0.0686] | 8.0/9 |
| delay | flow_trigger | origin=collection | flow_trigger|delay=72|origin=collection | flow_trigger|delay=6|origin=collection | 9 | +0.0866 | [+0.0462, +0.1298] | 9.0/9 |
| delay | flow_trigger | origin=collection | flow_trigger|delay=72|origin=collection | flow_trigger|delay=24|origin=collection | 9 | +0.0493 | [+0.0206, +0.0774] | 7.0/9 |
| delay | flow_trigger | origin=collection | flow_trigger|delay=24|origin=collection | flow_trigger|delay=6|origin=collection | 9 | +0.0373 | [+0.0044, +0.0720] | 8.0/9 |
| delay | uniform | origin=arrival | uniform|delay=72|origin=arrival | uniform|delay=6|origin=arrival | 9 | +0.0601 | [+0.0304, +0.0876] | 7.0/9 |
| delay | uniform | origin=arrival | uniform|delay=72|origin=arrival | uniform|delay=24|origin=arrival | 9 | +0.0413 | [+0.0146, +0.0631] | 7.0/9 |
| delay | uniform | origin=arrival | uniform|delay=24|origin=arrival | uniform|delay=6|origin=arrival | 9 | +0.0188 | [+0.0091, +0.0308] | 9.0/9 |
| delay | uniform | origin=collection | uniform|delay=72|origin=collection | uniform|delay=6|origin=collection | 9 | +0.0520 | [+0.0179, +0.0825] | 8.0/9 |
| delay | uniform | origin=collection | uniform|delay=72|origin=collection | uniform|delay=24|origin=collection | 9 | +0.0332 | [+0.0053, +0.0563] | 8.0/9 |
| delay | uniform | origin=collection | uniform|delay=24|origin=collection | uniform|delay=6|origin=collection | 9 | +0.0188 | [+0.0101, +0.0286] | 9.0/9 |
| origin | deadline_only | delay=6h | deadline_only|delay=6|origin=collection | deadline_only|delay=6|origin=arrival | 9 | +0.0027 | [+0.0003, +0.0053] | 6.0/9 |
| origin | deadline_only | delay=24h | deadline_only|delay=24|origin=collection | deadline_only|delay=24|origin=arrival | 9 | +0.0092 | [+0.0007, +0.0184] | 6.0/9 |
| origin | deadline_only | delay=72h | deadline_only|delay=72|origin=collection | deadline_only|delay=72|origin=arrival | 9 | +0.0057 | [-0.0066, +0.0178] | 5.0/9 |
| origin | deadline_only | delay=168h | deadline_only|delay=168|origin=collection | deadline_only|delay=168|origin=arrival | 9 | +0.0062 | [-0.0501, +0.0583] | 5.0/9 |
| origin | flow_trigger | delay=6h | flow_trigger|delay=6|origin=collection | flow_trigger|delay=6|origin=arrival | 9 | +0.0024 | [-0.0000, +0.0048] | 5.0/9 |
| origin | flow_trigger | delay=24h | flow_trigger|delay=24|origin=collection | flow_trigger|delay=24|origin=arrival | 9 | +0.0068 | [-0.0021, +0.0161] | 6.0/9 |
| origin | flow_trigger | delay=72h | flow_trigger|delay=72|origin=collection | flow_trigger|delay=72|origin=arrival | 9 | +0.0023 | [-0.0102, +0.0152] | 4.0/9 |
| origin | flow_trigger | delay=168h | flow_trigger|delay=168|origin=collection | flow_trigger|delay=168|origin=arrival | 9 | -0.0071 | [-0.0488, +0.0290] | 4.0/9 |
| origin | uniform | delay=6h | uniform|delay=6|origin=collection | uniform|delay=6|origin=arrival | 9 | +0.0013 | [-0.0006, +0.0032] | 5.0/9 |
| origin | uniform | delay=24h | uniform|delay=24|origin=collection | uniform|delay=24|origin=arrival | 9 | +0.0013 | [-0.0080, +0.0105] | 5.0/9 |
| origin | uniform | delay=72h | uniform|delay=72|origin=collection | uniform|delay=72|origin=arrival | 9 | -0.0068 | [-0.0283, +0.0162] | 3.0/9 |
| origin | uniform | delay=168h | uniform|delay=168|origin=collection | uniform|delay=168|origin=arrival | 9 | +0.0057 | [-0.0393, +0.0470] | 4.0/9 |
