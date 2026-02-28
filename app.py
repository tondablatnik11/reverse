import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Reverzní Inženýrství Kategorií", page_icon="🕵️", layout="wide")

st.title("🕵️ Reverzní Inženýrství Zákaznické Logiky")
st.markdown("""
Tato aplikace spojí zákazníkovy výsledky (Kategorie E/N/O/OE) z **Auswertungu** s vašimi surovými daty 
(**LIKP, VEKP, Pick, TOsD**) a pomůže najít 100% pravidlo pro zařazení chybějících zakázek.
""")

# ==========================================
# 1. NAHRÁNÍ SOUBORŮ
# ==========================================
with st.expander("📁 Nahrajte všechny soubory", expanded=True):
    uploaded_files = st.file_uploader(
        "Vyberte Auswertung, LIKP, VEKP, Pick report a TOsD (CSV nebo XLSX)", 
        accept_multiple_files=True
    )

if not uploaded_files:
    st.info("Nahrajte prosím soubory pro zahájení analýzy.")
    st.stop()

# ==========================================
# 2. ZPRACOVÁNÍ DAT
# ==========================================
with st.spinner("Zpracovávám a analyzuji soubory..."):
    df_truth = pd.DataFrame()
    df_pick = pd.DataFrame()
    df_likp = pd.DataFrame()
    df_vekp = pd.DataFrame()
    df_queue = pd.DataFrame()

    for file in uploaded_files:
        fname = file.name.lower()
        
        try:
            # Auswertung - Hledáme pravdu (Kategorie)
            if 'auswertung' in fname:
                aus_xl = pd.ExcelFile(file)
                # Zkusíme najít list s kategoriemi
                for sheet in ['Lieferungen Übersicht', 'HU Übersicht', 'Lieferpositionen Übersicht']:
                    if sheet in aus_xl.sheet_names:
                        tmp = aus_xl.parse(sheet, dtype=str)
                        if 'Lieferung' in tmp.columns and 'Kategorie' in tmp.columns:
                            df_truth = tmp[['Lieferung', 'Kategorie']].dropna().drop_duplicates('Lieferung')
                            break
            # Pick report
            elif 'pick' in fname:
                df_pick = pd.read_csv(file, dtype=str) if fname.endswith('.csv') else pd.read_excel(file, dtype=str)
            # TOsD (Queue)
            elif 'tosd' in fname or 'queue' in fname:
                df_queue = pd.read_csv(file, dtype=str) if fname.endswith('.csv') else pd.read_excel(file, dtype=str)
            # LIKP
            elif 'likp' in fname:
                df_likp = pd.read_csv(file, dtype=str) if fname.endswith('.csv') else pd.read_excel(file, dtype=str)
            # VEKP
            elif 'vekp' in fname:
                df_vekp = pd.read_csv(file, dtype=str) if fname.endswith('.csv') else pd.read_excel(file, dtype=str)
                
        except Exception as e:
            st.error(f"Chyba při čtení {file.name}: {e}")

    # ==========================================
    # 3. EXTRAKCE KLÍČOVÝCH VLASTNOSTÍ
    # ==========================================
    if df_truth.empty:
        st.error("❌ V Auswertungu se nepodařilo najít list s 'Lieferung' a 'Kategorie'.")
        st.stop()

    st.success(f"✅ Načtena 'Pravda' z Auswertungu pro **{len(df_truth)}** unikátních zásilek.")
    df_truth['Lieferung'] = df_truth['Lieferung'].astype(str).str.strip()

    # Příprava sjednocené tabulky
    master_df = df_truth.copy()

    # A. Přidání Queue z TOsD
    if not df_queue.empty and 'SD Document' in df_queue.columns and 'Queue' in df_queue.columns:
        q_map = df_queue.dropna(subset=['SD Document', 'Queue']).drop_duplicates('SD Document').set_index('SD Document')['Queue'].to_dict()
        master_df['Queue'] = master_df['Lieferung'].map(q_map)
    # Záložní Queue z Pick reportu (pokud je tam uložena)
    elif not df_pick.empty and 'Delivery' in df_pick.columns and 'Queue' in df_pick.columns:
        q_map = df_pick.dropna(subset=['Delivery', 'Queue']).drop_duplicates('Delivery').set_index('Delivery')['Queue'].to_dict()
        master_df['Queue'] = master_df['Lieferung'].map(q_map)

    # B. Přidání dat z LIKP (Versandstelle, Váha)
    if not df_likp.empty:
        c_del = next((c for c in df_likp.columns if 'Delivery' in str(c) or 'Lieferung' in str(c)), None)
        c_vs = next((c for c in df_likp.columns if 'Shipping Point' in str(c) or 'Versandstelle' in str(c)), None)
        c_wt = next((c for c in df_likp.columns if 'Total Weight' in str(c) or 'Gesamtgewicht' in str(c)), None)
        
        if c_del:
            df_likp[c_del] = df_likp[c_del].astype(str).str.strip()
            likp_clean = df_likp.drop_duplicates(c_del).set_index(c_del)
            if c_vs: master_df['Versandstelle'] = master_df['Lieferung'].map(likp_clean[c_vs])
            if c_wt: master_df['Total_Weight'] = pd.to_numeric(master_df['Lieferung'].map(likp_clean[c_wt]), errors='coerce')

    # C. Přidání typů obalů z VEKP
    if not df_vekp.empty:
        c_del_v = next((c for c in df_vekp.columns if 'Generated delivery' in str(c) or 'generierte Lieferung' in str(c)), None)
        c_pm = next((c for c in df_vekp.columns if 'Packaging materials' in str(c) or 'Packmittel' in str(c)), None)
        
        if c_del_v and c_pm:
            df_vekp[c_del_v] = df_vekp[c_del_v].astype(str).str.strip()
            # Spojení všech typů krabic pro jednu dodávku do stringu
            pm_map = df_vekp.dropna(subset=[c_del_v, c_pm]).groupby(c_del_v)[c_pm].apply(lambda x: ", ".join(sorted(set(x)))).to_dict()
            master_df['Obaly (VEKP)'] = master_df['Lieferung'].map(pm_map)

    # Vyčistíme N/A pro pivoty
    master_df = master_df.fillna('Nezjištěno')

# ==========================================
# 4. ZOBRAZENÍ VÝSLEDKŮ A MATIC SHODY
# ==========================================
st.divider()
st.header("📊 Výsledky analýzy: Hledání 100% shody")

tab1, tab2, tab3, tab4 = st.tabs(["🎯 Shoda podle Queue", "🏭 Shoda podle Místa odeslání (LIKP)", "📦 Shoda podle Obalu (VEKP)", "📋 Kompletní spojená data"])

# TAB 1: QUEUE
with tab1:
    st.subheader("Závislost: Tvoje Queue vs Zákazníkova Kategorie")
    st.markdown("Pokud v řádku (např. u PI_PA) vidíš čísla jen v jednom sloupci (např. 'E') a jinde nuly, našli jsme 100% pravidlo!")
    if 'Queue' in master_df.columns:
        pivot_q = pd.crosstab(master_df['Queue'], master_df['Kategorie'], margins=True, margins_name="Celkem")
        st.dataframe(pivot_q, use_container_width=True)
    else:
        st.warning("Data o Queue nebyla nalezena. Zkontrolujte napojení TOsD.")

# TAB 2: VERSANDSTELLE
with tab2:
    st.subheader("Závislost: Shipping Point (LIKP) vs Kategorie")
    if 'Versandstelle' in master_df.columns:
        pivot_vs = pd.crosstab(master_df['Versandstelle'], master_df['Kategorie'], margins=True, margins_name="Celkem")
        st.dataframe(pivot_vs, use_container_width=True)
    else:
        st.warning("Data o Versandstelle (LIKP) nebyla nalezena.")

# TAB 3: OBALY
with tab3:
    st.subheader("Závislost: Použitý obal (VEKP) vs Kategorie")
    if 'Obaly (VEKP)' in master_df.columns:
        pivot_pm = pd.crosstab(master_df['Obaly (VEKP)'], master_df['Kategorie'], margins=True, margins_name="Celkem")
        st.dataframe(pivot_pm, use_container_width=True)
    else:
        st.warning("Data o obalech (VEKP) nebyla nalezena.")

# TAB 4: KOMPLETNÍ DATA EXPORT
with tab4:
    st.subheader("Master Tabulka (Všechna data spojena přes Lieferung)")
    st.dataframe(master_df)
    
    # Export do Excelu
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        master_df.to_excel(writer, index=False, sheet_name='Spojena_Data')
        if 'Queue' in master_df.columns:
            pd.crosstab(master_df['Queue'], master_df['Kategorie']).to_excel(writer, sheet_name='Pivot_Queue')
            
    st.download_button(
        label="📥 Stáhnout data pro Excel",
        data=buffer.getvalue(),
        file_name="Reverse_Engineering_Data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
