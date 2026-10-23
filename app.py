
import os
import re
import gdown
import pandas as pd
import streamlit as st

# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="IMDb Movie Explorer",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 IMDb Movie Explorer")
st.write(
    "Explore movie ratings, genres, release years, "
    "and popular titles using IMDb data."
)

# --------------------------------------------------
# GOOGLE DRIVE DATASET
# --------------------------------------------------
FILE_ID = "1892UMet3AV8WBHyHXn4g9lHLj7HqsKzw"
CSV_PATH = "imdb_all_rated_movies.csv"


@st.cache_data(show_spinner=False)
def download_dataset():
    if not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0:
        url = f"https://drive.google.com/uc?id={FILE_ID}"
        result = gdown.download(
            url,
            CSV_PATH,
            quiet=False
        )

        if not result or not os.path.exists(CSV_PATH):
            raise RuntimeError(
                "Download failed. Check that the Google Drive "
                "file is shared with Anyone with the link."
            )

    return CSV_PATH


# --------------------------------------------------
# LOAD ONLY THE COLUMNS NEEDED BY THE APP
# This helps reduce memory usage for large datasets.
# --------------------------------------------------
COLUMN_ALIASES = {
    "title": [
        "primaryTitle", "originalTitle", "title",
        "movietitle", "name"
    ],
    "year": ["startYear", "year", "releaseYear"],
    "rating": ["averageRating", "rating", "imdbRating"],
    "votes": ["numVotes", "votes", "voteCount"],
    "genres": ["genres", "genre"],
    "runtime": ["runtimeMinutes", "runtime", "duration"],
}


def normalize_column(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


@st.cache_data(show_spinner="Loading IMDb dataset...")
def load_dataset(path):
    # Read just the header first.
    headers = pd.read_csv(path, nrows=0).columns.tolist()

    lookup = {normalize_column(c): c for c in headers}
    selected = {}

    for standard_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            original = lookup.get(normalize_column(alias))
            if original is not None:
                selected[standard_name] = original
                break

    if "title" not in selected:
        raise ValueError(
            "Could not find a movie title column. "
            f"Available columns: {headers}"
        )

    # Read only the columns the app needs.
    usecols = list(dict.fromkeys(selected.values()))

    data = pd.read_csv(
        path,
        usecols=usecols,
        low_memory=False
    )

    # Rename detected columns to consistent names.
    reverse_mapping = {
        original: standard
        for standard, original in selected.items()
    }
    data = data.rename(columns=reverse_mapping)

    # Convert numeric columns safely.
    for column in ["year", "rating", "votes", "runtime"]:
        if column in data.columns:
            data[column] = pd.to_numeric(
                data[column].replace("\\N", pd.NA),
                errors="coerce"
            )

    data["title"] = data["title"].fillna("Unknown").astype(str)

    if "genres" not in data.columns:
        data["genres"] = "Unknown"
    else:
        data["genres"] = (
            data["genres"]
            .fillna("Unknown")
            .replace("\\N", "Unknown")
            .astype(str)
        )

    return data


# --------------------------------------------------
# DOWNLOAD AND LOAD
# --------------------------------------------------
try:
    csv_file = download_dataset()
    df = load_dataset(csv_file)
except Exception as error:
    st.error(f"Could not load the IMDb dataset: {error}")
    st.info(
        "Check your Google Drive sharing settings and make "
        "sure the file ID points to your CSV."
    )
    st.stop()


if df.empty:
    st.warning("The dataset contains no rows.")
    st.stop()


# --------------------------------------------------
# SIDEBAR FILTERS
# --------------------------------------------------
st.sidebar.header("🔎 Filter Movies")

filtered = df.copy()

if "year" in df.columns and df["year"].notna().any():
    years = df["year"].dropna()
    min_year = int(years.min())
    max_year = int(years.max())

    if min_year < max_year:
        year_range = st.sidebar.slider(
            "Release year",
            min_value=min_year,
            max_value=max_year,
            value=(min_year, max_year)
        )
        filtered = filtered[
            filtered["year"].between(
                year_range[0], year_range[1]
            )
            | filtered["year"].isna()
        ]

if "rating" in df.columns and df["rating"].notna().any():
    min_rating = st.sidebar.slider(
        "Minimum IMDb rating",
        min_value=0.0,
        max_value=10.0,
        value=0.0,
        step=0.5
    )
    filtered = filtered[
        (filtered["rating"] >= min_rating)
        | filtered["rating"].isna()
    ]

available_genres = sorted({
    genre.strip()
    for value in df["genres"].dropna()
    for genre in value.split(",")
    if genre.strip() and genre.strip() != "Unknown"
})

if available_genres:
    selected_genres = st.sidebar.multiselect(
        "Genres",
        options=available_genres
    )

    if selected_genres:
        pattern = "|".join(
            re.escape(genre) for genre in selected_genres
        )
        filtered = filtered[
            filtered["genres"].str.contains(
                pattern, case=False, na=False, regex=True
            )
        ]

search_text = st.sidebar.text_input("Search movie titles")

if search_text:
    filtered = filtered[
        filtered["title"].str.contains(
            search_text, case=False, na=False, regex=False
        )
    ]


# --------------------------------------------------
# SUMMARY METRICS
# --------------------------------------------------
st.subheader("📊 Dataset Overview")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Movies", f"{len(filtered):,}")
col2.metric("Genres", f"{len(available_genres):,}")

if "rating" in filtered.columns:
    avg_rating = filtered["rating"].mean()
    col3.metric(
        "Average Rating",
        f"{avg_rating:.2f}/10" if pd.notna(avg_rating) else "N/A"
    )
else:
    col3.metric("Average Rating", "Not available")

if "votes" in filtered.columns:
    total_votes = filtered["votes"].sum()
    col4.metric(
        "Total Votes",
        f"{total_votes:,.0f}" if pd.notna(total_votes) else "N/A"
    )
else:
    col4.metric("Total Votes", "Not available")


st.caption(
    f"Showing {len(filtered):,} of {len(df):,} dataset rows."
)


# --------------------------------------------------
# TOP-RATED MOVIES
# --------------------------------------------------
st.subheader("🏆 Top-Rated Movies")

if "rating" in filtered.columns:
    ranked = filtered.dropna(subset=["rating"]).copy()

    if "votes" in ranked.columns:
        min_votes = st.number_input(
            "Minimum number of votes for ranking",
            min_value=0,
            value=1000,
            step=100
        )
        ranked = ranked[
            ranked["votes"].fillna(0) >= min_votes
        ]

    ranked = ranked.sort_values(
        "rating", ascending=False
    ).head(20)

    display_columns = [
        c for c in [
            "title", "year", "genres",
            "rating", "votes", "runtime"
        ]
        if c in ranked.columns
    ]

    if ranked.empty:
        st.info("No movies match the current filters.")
    else:
        st.dataframe(
            ranked[display_columns],
            use_container_width=True,
            hide_index=True
        )
else:
    st.info("A rating column was not found in this dataset.")


# --------------------------------------------------
# RATING DISTRIBUTION
# --------------------------------------------------
st.subheader("⭐ Rating Distribution")

if "rating" in filtered.columns:
    rating_data = filtered["rating"].dropna()

    if not rating_data.empty:
        histogram = pd.cut(
            rating_data,
            bins=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            include_lowest=True
        ).value_counts().sort_index()

        histogram.index = [
            f"{interval.left:.0f}–{interval.right:.0f}"
            for interval in histogram.index
        ]

        st.bar_chart(histogram)
    else:
        st.info("No ratings are available for these filters.")


# --------------------------------------------------
# GENRE ANALYSIS
# --------------------------------------------------
st.subheader("🎭 Movies by Genre")

genre_series = (
    filtered.assign(
        genre=filtered["genres"].str.split(",")
    )
    .explode("genre")
)

genre_series["genre"] = genre_series["genre"].str.strip()

genre_counts = (
    genre_series[
        genre_series["genre"].notna()
        & (genre_series["genre"] != "Unknown")
        & (genre_series["genre"] != "")
    ]["genre"]
    .value_counts()
    .head(15)
)

if not genre_counts.empty:
    st.bar_chart(genre_counts)
else:
    st.info("No genre information is available.")


# --------------------------------------------------
# YEAR-WISE TRENDS
# --------------------------------------------------
st.subheader("📅 Movies Released by Year")

if "year" in filtered.columns:
    year_counts = (
        filtered.dropna(subset=["year"])
        .groupby("year")
        .size()
        .sort_index()
    )

    if not year_counts.empty:
        year_counts.index = year_counts.index.astype(int).astype(str)
        st.line_chart(year_counts)
    else:
        st.info("No release-year information is available.")


# --------------------------------------------------
# DOWNLOAD FILTERED RESULTS
# --------------------------------------------------
st.subheader("⬇️ Export Results")

st.download_button(
    label="Download filtered movies as CSV",
    data=filtered.to_csv(index=False).encode("utf-8"),
    file_name="filtered_imdb_movies.csv",
    mime="text/csv"
)

st.caption("Data source: your IMDb dataset stored in Google Drive.")

