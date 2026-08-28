from pathlib import Path
import csv, json, random
from datetime import date, timedelta
from decimal import Decimal

random.seed(42)
out = Path(__file__).resolve().parents[2] / "data" / "generated"
out.mkdir(parents=True, exist_ok=True)
orders=[]; txns=[]; settlements=[]; batches={}
ground_truth=[]

base=date(2026,8,1)
def money(x): return f"{Decimal(x):.2f}"
def add_txn(order, batch, gross=None, fee=10, net=None, currency="INR", days=1, txn_id=None):
    gross=Decimal(gross if gross is not None else order["order_amount"])
    fee=Decimal(fee)
    net=Decimal(net if net is not None else gross-fee)
    t={"txn_id":txn_id or f"TXN-{len(txns)+1:04d}","order_ref":order["order_id"],"gross_amount":money(gross),"fee":money(fee),"net_amount":money(net),"currency":currency,"txn_date":str(base+timedelta(days=days)),"settlement_batch_id":batch}
    txns.append(t); batches.setdefault(batch,[]).append(t)

for i in range(60):
    amount=Decimal(random.choice([500,750,1000,1250,1500,2000]))
    od=base+timedelta(days=i%20)
    orders.append({"order_id":f"ORD-{i+1:04d}","customer_ref":f"CUST-{i+1:03d}","order_amount":money(amount),"currency":"INR","order_date":str(od),"expected_settlement_by":str(od+timedelta(days=2)),"status":"paid"})

# Evaluator-only labels. This file is never loaded by the inference path.
for i in range(60):
    ground_truth.append({
        "order_id": orders[i]["order_id"],
        "expected_outcome": "RECONCILED" if i < 40 else "ESCALATE",
        "scenario": "clean" if i < 40 else "injected_exception",
    })
ground_truth[0]["expected_outcome"] = "ESCALATE"
ground_truth[0]["scenario"] = "duplicate_key"
ground_truth[1]["expected_outcome"] = "ESCALATE"
ground_truth[1]["scenario"] = "duplicate_key"

# 40 clean
for i in range(40):
    add_txn(orders[i], f"SET-{i//5+1:03d}", days=1)

# Exceptions: amount, missing x4, duplicate x3, broken x3, late x2, currency, unresolved batch x3
add_txn(orders[40], "SET-009", gross=Decimal(orders[40]["order_amount"])+20)
add_txn(orders[41], "SET-009", fee=10, net=Decimal(orders[41]["order_amount"])-30) # bad arithmetic
# orders 42-45 missing
for i in range(46,49):
    add_txn(orders[i], "SET-010"); add_txn(orders[i], "SET-010") # duplicates
for i in range(49,52):
    add_txn(orders[i], None)
for i in range(52,54):
    add_txn(orders[i], "SET-011", days=1)
    orders[i]["expected_settlement_by"]=str(base) # deliberately late
add_txn(orders[54], "SET-012", currency="USD")
for i in range(55,58):
    add_txn(orders[i], "SET-013")
# malformed / negative linked order cases
add_txn(orders[58], "SET-014", txn_id="TXN-MALFORM")
txns[-1]["gross_amount"]="not-a-number"
add_txn(orders[59], "SET-014", txn_id="TXN-NEG")
txns[-1]["net_amount"]="-10.00"

# Create settlements from trusted numeric transaction sums.
for batch, members in batches.items():
    total=Decimal("0")
    for t in members:
        try:
            n=Decimal(t["net_amount"])
            if n >= 0: total += n
        except: pass
    settlements.append({"settlement_batch_id":batch,"credited_amount":money(total),"value_date":str(base+timedelta(days=2)),"utr_reference":f"UTR-{batch}"})
# Force one unresolved batch mismatch for SET-013 (three orders)
for s in settlements:
    if s["settlement_batch_id"]=="SET-013": s["credited_amount"]=money(Decimal(s["credited_amount"])+25)
# orphan bank settlement
settlements.append({"settlement_batch_id":"SET-ORPHAN","credited_amount":"999.00","value_date":str(base+timedelta(days=2)),"utr_reference":"UTR-ORPHAN"})
# unresolvable refs + duplicate key incident
for j in range(2):
    txns.append({"txn_id":f"TXN-ORPH-{j}","order_ref":"ORD-DOES-NOT-EXIST","gross_amount":"100.00","fee":"2.00","net_amount":"98.00","currency":"INR","txn_date":str(base),"settlement_batch_id":"SET-X"})
txns.append({"txn_id":"TXN-DUP","order_ref":orders[0]["order_id"],"gross_amount":"100.00","fee":"2.00","net_amount":"98.00","currency":"INR","txn_date":str(base),"settlement_batch_id":"SET-DUP"})
txns.append({"txn_id":"TXN-DUP","order_ref":orders[1]["order_id"],"gross_amount":"100.00","fee":"2.00","net_amount":"98.00","currency":"INR","txn_date":str(base),"settlement_batch_id":"SET-DUP"})

def write(name, rows):
    with (out/name).open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
write("orders.csv",orders); write("gateway_transactions.csv",txns); write("bank_settlements.csv",settlements)
with (out / "ground_truth.json").open("w", encoding="utf-8") as f:
    json.dump(ground_truth, f, indent=2)
print("Generated", len(orders), "orders,", len(txns), "transactions,", len(settlements), "settlements")
