import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
from datetime import datetime
import os
import requests
from io import BytesIO
from PIL import Image
import json
import ast
import seaborn as sns
import matplotlib.pyplot as plt

st.set_page_config(page_title="Buscador de Películas y Series", layout="wide")
st.title("🎬 Buscador de Películas y Series")

TIPOS_TRADUCCION = {
    'flatrate': 'Suscripción',
    'rent': 'Alquiler',
    'buy': 'Compra',
    'free': 'Gratis',
    'ads': 'Con publicidad',
}

@st.cache_data(ttl=1800, show_spinner="Cargando datos...")
def load_data():
    conn = sqlite3.connect("web-mining/data.db")

    df_movies = pd.read_sql("""
        SELECT ID, Titulo AS title, Titulo_Original as original_title, Idioma_Original AS language, 
               Fecha_de_Estreno AS release_date, Puntaje_Promedio AS rating,
               Cantidad_de_Votos AS votes, Poster_Path AS poster, 'movie' AS type,
               Popularidad, Generos
        FROM movies_tmdb_filt
        WHERE Fecha_de_Estreno >= '1900-01-01'
        """, conn, parse_dates=['release_date'])

    df_series = pd.read_sql("""
        SELECT ID, Nombre AS title, Nombre_Original as original_title, Idioma_Original AS language, 
               Anio_de_Inicio AS release_date, Puntaje_Promedio AS rating,
               Cantidad_de_Votos AS votes, Poster_Path AS poster, 'series' AS type,
               Popularidad, Generos
        FROM series_tmdb_argentina_idioma
        WHERE Anio_de_Inicio >= '1900'
        """, conn, parse_dates=['release_date'])

    df_movies['rating'] = pd.to_numeric(df_movies['rating'], downcast='float')
    df_movies['votes'] = pd.to_numeric(df_movies['votes'], downcast='integer')
    df_series['rating'] = pd.to_numeric(df_series['rating'], downcast='float')
    df_series['votes'] = pd.to_numeric(df_series['votes'], downcast='integer')
    df_series['votes'] = pd.to_numeric(df_series['votes'], downcast='integer')

    df = pd.concat([df_movies, df_series], ignore_index=True)
    df["release_year"] = df["release_date"].dt.year.astype('Int16')
    df.dropna(subset=["title"], inplace=True)

    # Providers y temporadas
    movie_prov = pd.read_sql("SELECT * FROM peliculas_providers", conn)
    series_seasons = pd.read_sql("SELECT * FROM series_providers_seasons_v2", conn)

    # Cargar el archivo CSV con los logos de los proveedores
    logos_df = pd.read_csv("web-minning/providers_logos.csv")


    conn.close()

    return df, movie_prov, series_seasons,logos_df

@st.cache_data(show_spinner=False)
def cargar_imagen_desde_url(url: str):
    try:
        response = requests.get(url, timeout=4)
        if response.status_code == 200:
            return Image.open(BytesIO(response.content))
    except:
        pass
    return None

# Cargar datos
movies_df, movie_providers, series_seasons, logos_df = load_data()
print(series_seasons)

import streamlit as st
import json
from datetime import datetime

# Valores por defecto
current_year = datetime.now().year

default_values = {
    "movie_title": "",
    "tipo_seleccionado": "Película",
    "year_filter": (1900, current_year),
    "rating_filter": (0.0, 10.0),
    "vote_filter": (0, 40000),
    "genre_filter": [],
    "provider_filter": "Todos"
}


# Inicializar los valores en session_state si no existen
for key, value in default_values.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Sidebar
st.sidebar.header("🔍 Filtros")

# Si se clickeó "Limpiar filtros", reiniciamos antes de instanciar widgets
if "reset_filters" in st.session_state and st.session_state.reset_filters:
    for key, val in default_values.items():
        st.session_state[key] = val
    st.session_state.reset_filters = False
    st.rerun()

# Inputs con session_state
movie_title = st.sidebar.text_input("Buscar por título", st.session_state.movie_title, key="movie_title")
tipo_opciones = {
    "Película": "movie",
    "Serie": "series"
}
tipo_seleccionado = st.sidebar.radio("Tipo", list(tipo_opciones.keys()), index=list(tipo_opciones.keys()).index(st.session_state.tipo_seleccionado), key="tipo_seleccionado")
type_filter = tipo_opciones[st.session_state.tipo_seleccionado]

year_filter = st.sidebar.slider("Año de estreno", 1900, current_year, st.session_state.year_filter, key="year_filter")
rating_filter = st.sidebar.slider("Rating promedio", 0.0, 10.0, st.session_state.rating_filter, step=0.1, key="rating_filter")
vote_filter = st.sidebar.slider("Cantidad de votos", 0, 10000, st.session_state.vote_filter, step=1, key="vote_filter")

# Cargar géneros desde los archivos JSON
if type_filter == "movie":
    genre_file = "web-mining/genres_peliculas.json"
else:
    genre_file = "web-mining/genres_series.json"

with open(genre_file, "r") as f:
    genre_map = json.load(f)

all_genres = sorted(set(genre_map.values()))
genre_filter = st.sidebar.multiselect("Seleccionar género(s)", all_genres, default=st.session_state.genre_filter, key="genre_filter")

# Filtro por proveedor
provider_list = sorted(set(movie_providers["Provider"]).union(series_seasons["Provider_Name"].dropna()))
provider_filter = st.sidebar.selectbox("Filtrar por proveedor", ["Todos"] + provider_list, index=(["Todos"] + provider_list).index(st.session_state.provider_filter), key="provider_filter")


# Inicializar el estado de reset en st.session_state
if st.sidebar.button("🔄 Limpiar filtros"):
    st.session_state.reset_filters = True
    st.rerun()



# Aplicar los filtros normalmente
filtered_df = movies_df.query("type == @type_filter")

if movie_title:
    filtered_df = filtered_df[
        filtered_df["title"].str.contains(movie_title, case=False, na=False) |
        filtered_df["original_title"].str.contains(movie_title, case=False, na=False)
    ]

filtered_df = filtered_df[
    (filtered_df["release_year"].between(*year_filter)) &
    (filtered_df["rating"].between(*rating_filter)) &
    (filtered_df["votes"].between(*vote_filter))
]

if provider_filter != "Todos":
    if type_filter == "movie":
        ids = movie_providers[movie_providers["Provider"] == provider_filter]["ID"].unique()
    else:
        ids = series_seasons[series_seasons["Provider_Name"] == provider_filter]["ID"].unique()
    filtered_df = filtered_df[filtered_df["ID"].isin(ids)]


# Aplicar filtro por género
if genre_filter:
    def parse_genres(cell):
        try:
            genres = ast.literal_eval(cell)
            if isinstance(genres, list):
                return [genre_map.get(str(g), g) for g in genres]
            else:
                return [genre_map.get(str(genres), genres)]
        except:
            return []

    filtered_df["parsed_genres"] = filtered_df["Generos"].apply(parse_genres)
    filtered_df = filtered_df[
        filtered_df["parsed_genres"].apply(lambda x: any(g in genre_filter for g in x))
    ]


# Tabs
tab1, tab2, tab3 = st.tabs(["📋 Resultados", "📊 Gráficos Filtrados", "📊 Gráficos Generales"])


with tab1:
    st.subheader("Resultados de búsqueda")
    if filtered_df.empty:
        st.warning("No se encontraron resultados.")
    else:
        PAGE_SIZE = 10
        total_pages = (len(filtered_df) - 1) // PAGE_SIZE + 1
        page_number = st.selectbox("Página", range(1, total_pages + 1))

        start_idx = (page_number - 1) * PAGE_SIZE
        end_idx = start_idx + PAGE_SIZE
        for _, row in filtered_df.iloc[start_idx:end_idx].iterrows():
            col1, col2 = st.columns([1, 2])
            with col1:
                poster_path = str(row.get("poster", "")).strip()

                if poster_path and poster_path.lower() not in ["none", "nan"] and not poster_path.isspace():
                    if not poster_path.startswith("/"):
                        poster_path = "/" + poster_path
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                else:
                    poster_url = "https://upload.wikimedia.org/wikipedia/commons/1/14/No_Image_Available.jpg"

                img = cargar_imagen_desde_url(poster_url)
                if img:
                    st.image(img, use_container_width=True)
                else:
                    st.image("https://upload.wikimedia.org/wikipedia/commons/1/14/No_Image_Available.jpg", use_container_width=True)
            with col2:
                st.markdown(f"### {row['title']} ({int(row['release_year'])})")
                st.markdown(f"- 🌐 **Idioma original**: {row['language']}")
                st.markdown(f"- ⭐ **Rating promedio**: {round(row['rating'], 1)}  / 10")
                st.markdown(f"- 🗳️ **Cantidad de votos**: {row['votes']}")


                # Mostrar disponibilidad por proveedor
                if row['type'] == 'movie':
                    provs = movie_providers[movie_providers['ID'] == row['ID']]
                else:
                    provs = series_seasons[series_seasons['ID'] == row['ID']]

                # Normalizar columna Provider
                if 'Provider' not in provs.columns and 'Provider_Name' in provs.columns:
                    provs = provs.rename(columns={'Provider_Name': 'Provider'})

                # Limpiar valores vacíos o nulos
                provs = provs[provs['Provider'].notna() & (provs['Provider'].str.strip() != '')]

                st.markdown("**📂 Disponibilidad por proveedor:**")

                if not provs.empty:
                    if row['type'] == 'series':
                        # Mostramos por temporadas para series
                        grouped = provs.dropna(subset=['Temporada']).groupby('Provider')['Temporada'].apply(list).reset_index()
                        for _, item in grouped.iterrows():
                            provider = item['Provider']
                            # Buscar el logo correspondiente al proveedor
                            logo_url = logos_df[logos_df['Provider'] == provider]['Logo_URL'].values
                            #logo_html = f"<img src='{logo_url[0]}' width='30' style='margin-right: 10px;' />" if logo_url else ""
                            logo_html = f"<img src='{logo_url[0]}' width='30' style='margin-right: 10px;' />" if len(logo_url) > 0 else ""

                            temporadas = sorted(set(int(t) for t in item['Temporada'] if pd.notnull(t)))
                            # Concatenar el logo y el nombre del proveedor
                            st.markdown(f"- {logo_html}<strong>{provider}</strong>: {', '.join(map(str, temporadas))}", unsafe_allow_html=True)
                    else:
                        # Para películas mostramos el tipo de disponibilidad
                        provs['Provider'] = provs['Provider'].str.strip().str.replace(r'\s+', ' ', regex=True)
                        grouped = provs.groupby('Provider')['Tipo'].apply(lambda x: ", ".join(x.dropna().unique())).reset_index()
                        for _, p in grouped.iterrows():
                            name = p['Provider']
                            # Buscar el logo correspondiente al proveedor
                            logo_url = logos_df[logos_df['Provider'] == name]['Logo_URL'].values
                            if len(logo_url) > 0:
                                logo_html = f"<img src='{logo_url[0]}' width='30' style='margin-right: 10px;' />"
                            else:
                                logo_html = ""
                            tipo_en = p['Tipo']
                            # Traducimos los tipos al español
                            tipo_map = {
                                'rent': 'Alquiler',
                                'buy': 'Compra',
                                'flatrate': 'Suscripción'
                            }
                            tipos_es = ", ".join([tipo_map.get(t.strip(), t.strip()) for t in tipo_en.split(",")])
                            # Concatenar el logo y el nombre del proveedor
                            st.markdown(f"- {logo_html}<strong>{name}</strong> ({tipos_es or '-'})", unsafe_allow_html=True)

                else:
                    st.markdown("❌ *No hay disponibilidad en Argentina para este título.*")

with tab2:
    if filtered_df.empty:
        st.info("No hay datos para graficar.")
    else:
        st.subheader("Rating promedio")
        filtered_df["rating"] = filtered_df["rating"].round(1)
        fig1 = px.bar(filtered_df.head(20), x="title", y="rating", color="rating",
                      labels={"title": "Título", "rating": "Rating promedio"})
        st.plotly_chart(fig1, use_container_width=True)

        st.subheader("Cantidad de votos")
        fig2 = px.bar(filtered_df.head(20), x="title", y="votes", color="votes",
                      labels={"title": "Título", "votes": "Cantidad de votos"})
        st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Distribución de popularidad")
        fig3 = px.histogram(filtered_df, x="Popularidad", nbins=30,
                            labels={"Popularidad": "Popularidad"})
        st.plotly_chart(fig3, use_container_width=True)

        st.subheader("Puntaje promedio vs. Cantidad de votos")
        fig4 = px.scatter(
            filtered_df,
            x="votes",
            y="rating",
            size="Popularidad",
            hover_name="title",
            labels={"votes": "Cantidad de votos", "rating": "Rating promedio"}
        )
        st.plotly_chart(fig4, use_container_width=True)

        st.subheader("Top 10 títulos más populares")
        top_populares = filtered_df.sort_values(by="Popularidad", ascending=False).head(10)
        fig5 = px.bar(
            top_populares,
            x="Popularidad",
            y="title",
            orientation="h",
            labels={"title": "Título", "Popularidad": "Popularidad"}
        )
        st.plotly_chart(fig5, use_container_width=True)

        st.subheader("Top 10 títulos mejor valorados (con más de 100 votos)")
        top_rating = filtered_df[filtered_df["votes"] > 100].sort_values(by="rating", ascending=False).head(10)
        fig6 = px.bar(
            top_rating,
            x="title",
            y="rating",
            labels={"title": "Título", "rating": "Rating promedio"}
        )
        st.plotly_chart(fig6, use_container_width=True)



with tab3:
    st.subheader("Gráficos Generales")
    conn = sqlite3.connect("web-mining/data.db")

    st.subheader("Top proveedores en Argentina")

    if type_filter == "movie":
        df_provider = pd.read_sql("SELECT Provider FROM peliculas_providers", conn)
    else:
        df_provider = pd.read_sql("SELECT Provider_Name AS Provider FROM series_providers_seasons_v2", conn)

    df_provider = df_provider.dropna()
    top_providers = df_provider["Provider"].value_counts().head(15).reset_index()
    top_providers.columns = ["Proveedor", "Cantidad de títulos"]

    fig_top_providers = px.bar(top_providers, x="Proveedor", y="Cantidad de títulos")
    st.plotly_chart(fig_top_providers, use_container_width=True)


    st.subheader("Top 10 géneros más frecuentes")
    if type_filter == "movie":
        df_genres = pd.read_sql("SELECT Generos FROM movies_tmdb_filt", conn)
        genre_file = "web-mining/genres_peliculas.json"
    else:
        df_genres = pd.read_sql("SELECT Generos FROM series_tmdb_argentina_idioma", conn)
        genre_file = "web-mining/genres_series.json"

    df_genres = df_genres.dropna()

    def parse_genres(cell):
        try:
            genres = ast.literal_eval(cell)
            if isinstance(genres, list):
                return genres
            else:
                return [genres]
        except:
            return []

    df_genres["Generos"] = df_genres["Generos"].apply(parse_genres)
    exploded_genres = df_genres.explode("Generos")

    with open(genre_file, "r") as f:
        genre_map = json.load(f)

    exploded_genres["Generos"] = exploded_genres["Generos"].map(lambda x: genre_map.get(str(x), x))
    top_genres = exploded_genres["Generos"].value_counts().head(10).reset_index()
    top_genres.columns = ["Género", "Cantidad"]
    fig_top_genres = px.bar(top_genres, x="Género", y="Cantidad")
    st.plotly_chart(fig_top_genres, use_container_width=True)

    st.subheader("Distribución de ratings por género")
    if type_filter == "movie":
        df_ratings = pd.read_sql("SELECT Generos, Puntaje_Promedio FROM movies_tmdb_filt", conn)
    else:
        df_ratings = pd.read_sql("SELECT Generos, Puntaje_Promedio FROM series_tmdb_argentina_idioma", conn)

    df_ratings = df_ratings.dropna()
    df_ratings["Generos"] = df_ratings["Generos"].apply(parse_genres)
    df_ratings = df_ratings.explode("Generos")

    with open(genre_file, "r") as f:
        genre_map = json.load(f)

    df_ratings["Generos"] = df_ratings["Generos"].map(lambda x: genre_map.get(str(x), x))
    df_ratings.rename(columns={"Generos": "Género", "Puntaje_Promedio": "Rating"}, inplace=True)
    fig_box_rating = px.box(df_ratings, x="Género", y="Rating")
    st.plotly_chart(fig_box_rating, use_container_width=True)

    st.subheader("Cantidad de títulos estrenados por año")
    df_general = movies_df[movies_df["type"] == type_filter]
    estrenos_por_anio = df_general["release_year"].value_counts().sort_index().reset_index()
    estrenos_por_anio.columns = ["Año", "Cantidad de títulos"]
    fig_estrenos = px.line(estrenos_por_anio, x="Año", y="Cantidad de títulos", markers=True)
    st.plotly_chart(fig_estrenos, use_container_width=True)

    st.subheader("Rating promedio por año de estreno")
    rating_anual = df_general.groupby("release_year")["rating"].mean().reset_index()
    rating_anual.columns = ["Año", "Rating promedio"]
    fig_rating_anual = px.line(rating_anual, x="Año", y="Rating promedio", markers=True)
    st.plotly_chart(fig_rating_anual, use_container_width=True)

    st.subheader("Distribución de cantidad de votos")
    fig_votes_hist = px.histogram(df_general, x="votes", nbins=40, labels={"votes": "Cantidad de votos"})
    st.plotly_chart(fig_votes_hist, use_container_width=True)

    st.subheader("Idiomas originales más frecuentes")
    top_languages = df_general["language"].value_counts().head(10).reset_index()
    top_languages.columns = ["Idioma", "Cantidad"]
    fig_languages = px.bar(top_languages, x="Idioma", y="Cantidad")
    st.plotly_chart(fig_languages, use_container_width=True)
    
    conn.close()