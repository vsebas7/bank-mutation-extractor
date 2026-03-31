import streamlit as st
from services.db import get_plans

def show_upgrade_page():
    st.title("⬆️ Upgrade Plan")
    
    PLANS = get_plans()
    
    # Filter hanya pro & enterprise
    paid_plans = {k: v for k, v in PLANS.items() if k != "free"}
    
    cols = st.columns(len(paid_plans))
    
    for col, (plan_name, plan_data) in zip(cols, paid_plans.items()):
        with col:
            st.subheader(f"{plan_data['label']}")
            st.write(f"Rp {int(plan_data['price_monthly']):,}/bulan")
            st.write(f"Rp {int(plan_data['price_annual']):,}/tahun")
            st.write(f"✅ Upload {plan_data['max_pdf_per_session'] if plan_data['max_pdf_per_session'] != -1 else 'unlimited'} PDF")
            st.write(f"✅ Bank: {', '.join(b.upper() for b in plan_data['allowed_banks'])}")
            
            cycle = st.radio(
                "Billing",
                ["monthly", "annual"],
                key=f"cycle_{plan_name}",
                format_func=lambda x: "Bulanan" if x == "monthly" else "Tahunan"
            )
            
            if st.button(f"Pilih {plan_data['label']}", use_container_width=True, key=f"btn_{plan_name}"):
                from payment import create_invoice
                invoice = create_invoice(
                    user_email=st.session_state["user"].email,
                    plan=plan_name,
                    billing_cycle=cycle
                )
                st.link_button("💳 Bayar Sekarang", invoice["invoice_url"], use_container_width=True)