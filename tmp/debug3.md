First race link text: 4+Alw49.00
First race link href: /stables/race.aspx?raceid=22625001
  depth=0: <td class=[]>
  depth=1: <tr class=[] width=> direct_td_count=16
    first_td text: 20Feb26-1TP
  depth=3: <table class=['Arial7'] width=> direct_tr_count=0
  depth=4: <td class=[]>
  depth=5: <tr class=[] width=> direct_td_count=3
    first_td text: 
  depth=7: <table class=['Arial7'] width=740> direct_tr_count=0
  depth=8: <td class=[]>
  depth=9: <tr class=[] width=> direct_td_count=1
    first_td text: DisabledDisabledALB Fast/XXXXF
  depth=11: <table class=[] width=> direct_tr_count=0
  depth=12: <td class=[]>
  depth=13: <tr class=[] width=> direct_td_count=3
    first_td text: 

=== All TRs with race IDs in document ===
Total TRs in document: 197
  Race TR: 20Feb26-1TP | parent_table_class=['Arial7'] width= | nesting_depth=4
  Race TR: 14Jan26-2GP | parent_table_class=['Arial7'] width= | nesting_depth=4
  Race TR: 28Nov25-4PRX | parent_table_class=['Arial7'] width= | nesting_depth=4
Total race TRs (with race.aspx link, >=10 cells): 12

=== Testing different table traversal strategies ===
Strategy 1 (table.find_all('tr') no recursive): 48 (note: overcounts due to nested tables)
Strategy 2 (s.find_all('tr') deduped): 12