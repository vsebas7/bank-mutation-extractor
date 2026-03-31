import streamlit as st
from services.db      import get_plans, get_subscription, is_subscription_active
from services.payment import create_invoice


def show_upgrade_page():
    st.title("⬆️ Upgrade Plan")

    PLANS      = get_plans()
    sub        = get_subscription()
    paid_plans = {k: v for k, v in PLANS.items() if k != "free"}

    cols = st.columns(len(paid_plans))

    for col, (plan_name, plan_data) in zip(cols, paid_plans.items()):
        with col:
            st.subheader(plan_data["label"])
            st.write(f"Rp {int(plan_data['price_monthly']):,}/bulan")
            st.write(f"Rp {int(plan_data['price_annual']):,}/tahun")
            st.write(
                f"✅ Upload "
                f"{'unlimited' if plan_data['max_pdf_per_session'] == -1 else plan_data['max_pdf_per_session']}"
                f" PDF"
            )
            st.write(f"✅ Bank: {', '.join(b.upper() for b in plan_data['allowed_banks'])}")
            st.write(
                f" Update Bank: "
                f"{'✅' if plan_data['max_pdf_per_session'] == -1 else '❌'}"
            )

            cycle = st.radio(
                "Billing",
                ["monthly", "annual"],
                key=f"cycle_{plan_name}",
                format_func=lambda x: "Bulanan" if x == "monthly" else "Tahunan",
            )

            is_current = (
                sub["plan"] == plan_name 
                and sub["billing_cycle"] == cycle
                and is_subscription_active()
            )
            
            if is_current:
                st.success("✅ Plan aktif kamu")

            if st.button(
                f"Pilih {plan_data['label']}",
                use_container_width=True,
                key=f"btn_{plan_name}",
                disabled=is_current,
            ):
                with st.spinner("Membuat invoice..."):
                    try:
                        invoice = create_invoice(
                            user_email=st.session_state["user"].email,
                            plan=plan_name,
                            billing_cycle=cycle,
                        )
                        st.link_button(
                            "💳 Bayar Sekarang",
                            invoice["invoice_url"],
                            use_container_width=True,
                        )
                    except Exception as e:
                        st.error(f"Gagal membuat invoice: {e}")
