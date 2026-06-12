"""
app.py
------
Streamlit application: EV Charging Station Demand Analysis (Berlin).

A crowdsourcing app to identify high-demand areas for EV charging stations:
- Heatmaps of residents and existing charging infrastructure by postal code
- User reporting of station malfunctions
- User suggestions for new station locations

Run with:  streamlit run app.py
"""

import folium
import streamlit as st
from streamlit_folium import st_folium

from core import methods, reports
import config

st.set_page_config(
    page_title="EV Charging Analytics Platform",
    page_icon="🔌",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Cached data loading
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading geodata …")
def get_geodata():
    return methods.load_geodata()


@st.cache_data(show_spinner="Loading residents data …")
def get_residents():
    return methods.load_residents()


@st.cache_data(show_spinner="Loading charging-station register …")
def get_stations():
    return methods.load_charging_stations()


# ---------------------------------------------------------------------------
# Sidebar — page navigation
# ---------------------------------------------------------------------------
st.sidebar.title("🔌 Berlin EV Demand")
page = st.sidebar.radio(
    "Navigate",
    (
        "📊 Heatmaps & Analysis",
        "📝 Report & Suggest",
        "🗂 Community Reports",
    ),
)
st.sidebar.markdown("---")
st.sidebar.caption(
    "Crowdsourcing app to identify high-demand areas for EV charging stations "
    "in Berlin. Report broken stations or suggest new locations directly on the map."
)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
try:
    gdf_geo = get_geodata()
    df_res = get_residents()
    df_st = get_stations()
except FileNotFoundError as e:
    st.error(
        f"**Dataset missing:** {e}\n\n"
        "Please place the required files in the `datasets/` folder "
        "(see README for download links)."
    )
    st.stop()

gdf_res = methods.make_residents_gdf(gdf_geo, df_res)
gdf_st = methods.make_stations_gdf(gdf_geo, df_st)
df_reports = reports.load_reports()


# ===========================================================================
# PAGE 1 — Heatmaps & Analysis
# ===========================================================================
if page == "📊 Heatmaps & Analysis":
    st.title("Heatmaps: Charging Stations & Residents in Berlin")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Postal codes", f"{len(gdf_geo):,}")
    c2.metric("Residents (total)", f"{int(gdf_res['Einwohner'].sum()):,}")
    c3.metric("Charging stations", f"{len(df_st):,}")
    c4.metric("Community reports", f"{len(df_reports):,}")

    layer = st.radio(
        "Select visualisation layer",
        (
            "Residents (population density)",
            "Charging stations (per postal code)",
            "Charging stations (point heatmap)",
            "Charging stations by nominal power (kW)",
        ),
        horizontal=True,
    )
    show_reports = st.checkbox("Overlay community reports on the map", value=True)

    if layer.startswith("Residents"):
        st.caption("Yellow = low density · Red = high density")
        fmap = methods.map_residents(gdf_res)
    elif layer == "Charging stations (per postal code)":
        st.caption("Light = few stations · Dark blue = many stations")
        fmap = methods.map_stations_choropleth(gdf_st)
    elif layer == "Charging stations (point heatmap)":
        st.caption("Darker colours represent higher density / power concentration")
        fmap = methods.map_stations_heatmap(df_st)
    else:
        st.caption("Toggle individual power classes in the map's layer control")
        fmap = methods.map_stations_by_power(df_st)

    if show_reports:
        fmap = reports.add_reports_layer(fmap, df_reports)

    st_folium(fmap, width=None, height=600, returned_objects=[])

    with st.expander("📊 Infrastructure gap analysis (high-demand areas)"):
        gap = gdf_res[["PLZ", "Einwohner"]].merge(
            gdf_st[["PLZ", "Stationen"]], on="PLZ"
        )
        gap["Residents per station"] = (
            gap["Einwohner"] / gap["Stationen"].replace(0, float("nan"))
        ).round(0)

        # Fold in crowdsourced signals: suggestions add demand evidence
        counts = reports.report_counts_by_plz(df_reports)
        gap = gap.merge(counts, on="PLZ", how="left").fillna(
            {"Malfunctions": 0, "Suggestions": 0}
        )
        gap = gap.sort_values("Residents per station", ascending=False)
        st.dataframe(
            gap.rename(columns={"Einwohner": "Residents", "Stationen": "Stations"}),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Postal codes at the top are the most underserved: many residents share "
            "few (or no) stations. User-submitted suggestions and malfunction reports "
            "provide additional on-the-ground demand evidence."
        )


# ===========================================================================
# PAGE 2 — Report & Suggest (crowdsourcing)
# ===========================================================================
elif page == "📝 Report & Suggest":
    st.title("Report a malfunction or suggest a new station")
    st.write(
        "Click on the map to drop a pin, then fill in the form. "
        "Red wrench markers are malfunction reports; green plus markers are "
        "suggested locations for new stations."
    )

    col_map, col_form = st.columns([3, 2])

    with col_map:
        fmap = methods.map_stations_choropleth(gdf_st)
        fmap = reports.add_reports_layer(fmap, df_reports)

        # Show the currently selected pin
        if "picked_location" in st.session_state:
            lat, lon = st.session_state["picked_location"]
            folium.Marker(
                [lat, lon],
                icon=folium.Icon(color="blue", icon="map-pin", prefix="fa"),
                tooltip="Your selected location",
            ).add_to(fmap)

        map_state = st_folium(
            fmap, width=None, height=520, returned_objects=["last_clicked"]
        )
        if map_state and map_state.get("last_clicked"):
            st.session_state["picked_location"] = (
                map_state["last_clicked"]["lat"],
                map_state["last_clicked"]["lng"],
            )

    with col_form:
        picked = st.session_state.get("picked_location")
        if picked:
            st.success(f"Selected location: {picked[0]:.5f}, {picked[1]:.5f}")
        else:
            st.info("👆 Click the map to select a location first.")

        with st.form("report_form", clear_on_submit=True):
            report_type = st.radio(
                "What would you like to do?",
                ("⚠️ Report a malfunctioning station", "💡 Suggest a new station location"),
            )
            plz = st.text_input("Postal code (optional)", max_chars=5,
                                placeholder="e.g. 10115")
            description = st.text_area(
                "Description *",
                placeholder=(
                    "e.g. 'Charger at this site has a broken display and won't "
                    "start a session' or 'Large residential area, nearest charger "
                    "is 1.5 km away'"
                ),
            )
            reporter = st.text_input("Your name (optional)", placeholder="anonymous")
            submitted = st.form_submit_button("Submit report", type="primary")

        if submitted:
            if not picked:
                st.error("Please click the map to select a location first.")
            elif not description.strip():
                st.error("Please enter a description.")
            else:
                rtype = (
                    reports.TYPE_MALFUNCTION
                    if report_type.startswith("⚠️")
                    else reports.TYPE_SUGGESTION
                )
                try:
                    reports.add_report(
                        rtype, picked[0], picked[1], description, plz, reporter
                    )
                    del st.session_state["picked_location"]
                    st.success("✅ Thank you! Your report has been saved.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ===========================================================================
# PAGE 3 — Community Reports
# ===========================================================================
else:
    st.title("Community reports")

    if df_reports.empty:
        st.info("No reports yet — be the first on the *Report & Suggest* page!")
    else:
        n_mal = (df_reports["type"] == reports.TYPE_MALFUNCTION).sum()
        n_sug = (df_reports["type"] == reports.TYPE_SUGGESTION).sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total reports", len(df_reports))
        c2.metric("⚠️ Malfunctions", int(n_mal))
        c3.metric("💡 Station suggestions", int(n_sug))

        filter_type = st.multiselect(
            "Filter by type",
            options=[reports.TYPE_MALFUNCTION, reports.TYPE_SUGGESTION],
            default=[reports.TYPE_MALFUNCTION, reports.TYPE_SUGGESTION],
            format_func=lambda t: "⚠️ Malfunction" if t == reports.TYPE_MALFUNCTION
            else "💡 Suggestion",
        )
        filtered = df_reports[df_reports["type"].isin(filter_type)]

        fmap = methods.map_stations_choropleth(gdf_st)
        fmap = reports.add_reports_layer(fmap, filtered)
        st_folium(fmap, width=None, height=500, returned_objects=[])

        st.dataframe(
            filtered.sort_values("timestamp", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "⬇️ Download reports as CSV",
            data=filtered.to_csv(index=False).encode("utf-8"),
            file_name="user_reports.csv",
            mime="text/csv",
        )
