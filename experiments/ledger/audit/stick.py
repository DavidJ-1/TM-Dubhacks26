"""'Do saves stick?' recompute on the final 184 (conservative costing). ALL NUMBERS SYNTHETIC.
Old row = ../economics/headline_1478.csv row 'per-account survival-weighted discounted (own hazard 24 mo)' x NEW guardrail:
58 contacts (re-picked with that value), break-even 0.0760, boot10_p_pos 0.428."""
import io, contextlib, json
with contextlib.redirect_stdout(io.StringIO()):
    import ledger as LG
from final_policy import *
Q = P.copy(); Q["V"] = V_SURV.reindex(Q.account_id).values         # same per-account survival value as priority.py P2
be = LG.be_stats(Q); b10 = LG.boot(Q, 0.10); b5 = LG.boot(Q, 0.05)
pos = acct(Q, s(0.10)) > 0
# old method (re-pick with that value + new guardrail), for reference
C2 = C0.copy(); C2["V"] = C2.account_id.map(V_SURV).values
rp, _ = pick_new(C2)
out = dict(policy="final 184, conservative costing, kept value = own-risk survival value",
           net_mid_10=round(float(acct(Q, s(0.10)).sum()), 0), accounts_positive_at_10=int(pos.sum()),
           breakeven_save_rate=round(be[0], 4), boot10_p_pos=b10["p_pos"], boot10_range=[b10["lo95"], b10["hi95"]], boot5_p_pos=b5["p_pos"],
           old_method_repick_contacts=len(rp), old_method_repick_breakeven=round(float(breakeven(rp)), 4), old_method_repick_boot10_p_pos=LG.boot(rp, 0.10)["p_pos"])
json.dump(out, open(HERE / "out_final" / "saves_stick.json", "w"), indent=1, default=float); print(out)
