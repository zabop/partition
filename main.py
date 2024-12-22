from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from xml.etree import ElementTree as ET
import geopandas as gpd
import shapely.geometry
from tqdm import tqdm
import numpy as np
import requests
import json

app = FastAPI()

origins = ["https://zabop.github.io", "*"]  # local dev

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["*"],
)

maxc = 20037508.342789244
sidelength = lambda z: 2 * maxc / (2**z)


def get_tile_centres(z, x, y):
    x = -maxc + maxc / (2**z) + sidelength(z) * x
    y = maxc - maxc / (2**z) - sidelength(z) * y
    return x, y


def get_tile_corners(z, x, y, exag=1):
    tc = get_tile_centres(z, x, y)
    s = sidelength(z)
    corners = []
    for each in [[1, 1], [1, -1], [-1, -1], [-1, 1], [1, 1]]:
        v = exag * 0.5 * np.array([each]) * np.array([s, s])
        corner = tc + v
        corners.append(corner)
    corners = np.squeeze(corners)
    p = shapely.geometry.Polygon(corners)
    return p


def epsg3857xyzoom_to_tileid(x, y, z, maxc=maxc):
    tilex = int(np.floor((x + maxc) * (2 ** (z - 1)) / maxc))
    tiley = int(np.floor((-y + maxc) * (2 ** (z - 1)) / maxc))
    return [z, tilex, tiley]


def get_border(osm_id):
    response = requests.get(
        f"https://polygons.openstreetmap.fr/get_geojson.py?id={osm_id}&params=0"
    )
    with open("/tmp/borders.geojsonseq", "wb") as f:
        f.write(response.content)

    with open("/tmp/borders.geojsonseq") as f:
        [data] = [json.loads(line) for line in f]

    gpd.GeoSeries([shapely.geometry.shape(data)]).to_file("/tmp/borders.geojson")


@app.get("/")
async def partition(feature_id: int, zoom: int):

    get_border(350377)
    z = 14

    df = gpd.read_file("borders.geojson").to_crs(3857)
    bounds = df.geometry.bounds

    boundary_xmin, boundary_ymin, boundary_xmax, boundary_ymax = (
        bounds.minx.min(),
        bounds.miny.min(),
        bounds.maxx.max(),
        bounds.maxy.max(),
    )

    _, xmin, ymin = epsg3857xyzoom_to_tileid(boundary_xmin, boundary_ymax, z)
    _, xmax, ymax = epsg3857xyzoom_to_tileid(boundary_xmax, boundary_ymin, z)

    polygonids = []
    for x in tqdm(range(xmin, xmax + 1), total=xmax - xmin + 1):
        for y in range(ymin, ymax + 1):
            if df.geometry.intersects(get_tile_corners(z, x, y)).any():
                polygonids.append([z, x, y])

    return {"polygonids": ", ".join(["/".join(each) for each in polygonids])}