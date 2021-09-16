import numpy as np
import gdal
import osr
from shapely.geometry import Polygon, Point
from shapely import affinity
import math

import pandas as pd
import geopandas as gpd

raster_path = r"C:\dev\Raster Preparer and ML Vectoriser\tifs\test_tif_utm30N.tif"
out_path = r"C:\dev\Raster Preparer and ML Vectoriser\tifs\polygonised.shp"

raster = gdal.Open(raster_path)
dst_crs = 'EPSG:'+str(osr.SpatialReference(wkt=raster.GetProjection()).GetAttrValue('AUTHORITY',1))
xoff, a, b, yoff, d, e = raster.GetGeoTransform()


# todo this should be placed in a function
# check if raster in UTM system. Re-projects if not.
if not dst_crs.split(":")[1].startswith('0') or not dst_crs.split(":")[1].startswith('326') or not dst_crs.split(":")[1].startswith('327'):
    determineUTMtif = None
    utm_band = str((math.floor((xoff + 180) / 6) % 60) + 1)
    if len(utm_band) == 1:
        utm_band = '0' + utm_band
    if yoff >= 0:
        epsg_code = '326' + utm_band
    else:
        epsg_code = '327' + utm_band
    dst_crs = 'EPSG:' + str(epsg_code)
    outputESPG = ''.join(ch for ch in dst_crs if ch.isalnum())

    # re-project
    print("Reprojecting tif into " + dst_crs)
    reprojected_raster_path = "\\".join(raster_path.split(".")[:-1]) + "_reprojected.tif"
    gdal.Warp(reprojected_raster_path, raster_path, format="GTiff", options=["COMPRESS=LZW", "TILED=YES"], dstSRS=dst_crs)

    # open new shiny UTM raster
    del raster
    raster = gdal.Open(reprojected_raster_path)
    dst_crs = 'EPSG:' + str(osr.SpatialReference(wkt=raster.GetProjection()).GetAttrValue('AUTHORITY', 1))
    xoff, a, b, yoff, d, e = raster.GetGeoTransform()


def outputSinglePixel(pxl):
    # outputs a point, for testing
    gpd.GeoDataFrame(pd.DataFrame(['p1'], columns=['geom']),
                     crs={'init': dst_crs},
                     geometry=[affinity.rotate(Point(pixel2point(pxl)), 180, (xoff, yoff))]).to_file(out_path)

def pixel2point(pxl):
    x,y = pxl
    posY = a * x + b * y + yoff
    posX = d * x + e * y + xoff
    #posX += (a/2)
    #posY += (a/2)
    return Point(posX, posY)


def outputResult(pnts):
    # buffering fixes self intersecting geometries
    # I can't tell you why the rotation is required
    # if multipolygon get largest
    vector_footprint = affinity.rotate(Polygon(pnts).buffer(0), 180, (xoff, yoff))
    if vector_footprint.geom_type == 'MultiPolygon':
        vector_footprint = max(vector_footprint, key=lambda a: a.area)

    print("outputting...")
    geoDF = gpd.GeoDataFrame(pd.DataFrame(['p1'], columns=['geom']),
                             crs={'init': dst_crs},
                             geometry=[vector_footprint])
    geoDF.to_file(out_path)



def getFlatArray(raster):
    # flattens raster bands into one array
    imarray = np.array(raster.ReadAsArray())
    flattenedarray = imarray[0]
    for i in range(1, imarray.shape[0]):
        flattenedarray = np.add(flattenedarray, imarray[i])

    return flattenedarray


def getStartingPixel(arr):
    # Scan the array until a pixel containing data is found
    for x in range(0, arr.shape[0] - 1):  # this is wrong its y,x but confusing to change
        for y in range(0, arr.shape[1] - 1):
            if arr[x, y] != 0:
                starting_pixel = (x, y)
                entry_pixel = (x, y-1)
                return starting_pixel, entry_pixel

def MooresBoundaryTrace(arr):
    # moores algorithm based on:
    # http://www.imageprocessingplace.com/downloads_V3/root_downloads/tutorials/contour_tracing_Abeer_George_Ghuneim/moore.html
    moores_neighbs = [(0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1)]  # clockwise

    starting_pixel, entry_pixel = getStartingPixel(arr)

    boundary = []
    boundary.append(starting_pixel)

    curr_x, curr_y = starting_pixel
    prev_x, prev_y = entry_pixel

    d_x = prev_x - curr_x
    d_y = prev_y - curr_y

    moores_idx = moores_neighbs.index((d_x, d_y))
    complete = False
    while not complete:
        # assign the pixel to check
        check_x, check_y = curr_x + moores_neighbs[moores_idx][0], curr_y + moores_neighbs[moores_idx][1]

        # if within array and contains data set as boundary
        if check_x >= 0 and check_y >= 0 and check_x < arr.shape[0] and check_y < arr.shape[1] and arr[check_x][check_y] != 0:
            curr_x, curr_y = check_x, check_y
            d_x, d_y = prev_x - curr_x, prev_y - curr_y
            moores_idx = moores_neighbs.index((d_x, d_y))
            if (curr_x, curr_y) in boundary:
                complete = True
            boundary.append((curr_x, curr_y))
        else:
            prev_x, prev_y = check_x, check_y
            moores_idx += 1
            if moores_idx == len(moores_neighbs):
                moores_idx = 0

    return boundary

if __name__ == "__main__":
    arr = getFlatArray(raster)
    boundary = MooresBoundaryTrace(arr)

    pnts = [pixel2point(pxl) for pxl in boundary]
    outputResult(pnts=pnts)