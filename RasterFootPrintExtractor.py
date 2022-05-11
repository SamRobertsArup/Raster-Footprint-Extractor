import numpy as np
import gdal
import osr
from shapely.geometry import Polygon, Point
from shapely import affinity
import math

import pandas as pd
import geopandas as gpd

class RasterFootPrintExtractor():
    def __init__(self, raster_path, out_path, no_data=0, output_CAD=False):
        self.result = None
        self.out_path = out_path
        self.output_CAD = output_CAD
        self.raster = gdal.Open(raster_path)
        self.dst_crs = int(osr.SpatialReference(wkt=self.raster.GetProjection()).GetAttrValue('AUTHORITY',1))  # 'EPSG:'+str(osr.SpatialReference(wkt=self.raster.GetProjection()).GetAttrValue('AUTHORITY',1))
        self.xoff, self.a, self.b, self.yoff, self.d, self.e = self.raster.GetGeoTransform()
        # check if raster in UTM system. Re-projects if not.
        # todo this should be placed in a function
        if not (
                str(self.dst_crs).startswith('0')
            or  str(self.dst_crs).startswith('326')
            or  str(self.dst_crs).startswith('327')
            or  str(self.dst_crs).startswith("27700")
        ):
            utm_band = str((math.floor((self.xoff + 180) / 6) % 60) + 1)
            if len(utm_band) == 1:
                utm_band = '0' + utm_band
            if self.yoff >= 0:
                epsg_code = '326' + utm_band
            else:
                epsg_code = '327' + utm_band
            dst_crs = 'EPSG:' + str(epsg_code)

            # re-project
            print("Reprojecting tif into " + dst_crs)
            reprojected_raster_path = "\\".join(raster_path.split(".")[:-1]) + "_reprojected.tif"
            gdal.Warp(reprojected_raster_path, raster_path, format="GTiff", options=["COMPRESS=LZW", "TILED=YES"], dstSRS=dst_crs)

            # open new shiny UTM raster
            del self.raster
            raster = gdal.Open(reprojected_raster_path)
            self.dst_crs =  int(osr.SpatialReference(wkt=raster.GetProjection()).GetAttrValue('AUTHORITY', 1))  # 'EPSG:' + str(osr.SpatialReference(wkt=raster.GetProjection()).GetAttrValue('AUTHORITY', 1))
            self.xoff, self.a, self.b, self.yoff, self.d, self.e = raster.GetGeoTransform()

        imarray = np.array(self.raster.ReadAsArray())
        if self.raster.GetRasterBand(self.raster.RasterCount).GetNoDataValue() is None:
            self.no_data = no_data * imarray.shape[0]
        elif no_data != 0:
            self.no_data = no_data * imarray.shape[0]
        else:
            self.no_data = self.raster.GetRasterBand(self.raster.RasterCount).GetNoDataValue() * imarray.shape[0]

        self.arr = imarray.sum(axis=0)  # flattened array
        self.boundary = self.MooresBoundaryTrace()

        self.pnts = [self.pixel2point(pxl) for pxl in self.boundary]
        self.outputResult()

    def outputSinglePixel(self, pxl):
        # outputs a point, for testing
        gpd.GeoDataFrame(pd.DataFrame(['p1'], columns=['geom']),
                         crs=self.dst_crs,
                         geometry=[affinity.rotate(Point(self.pixel2point(pxl)), 180, (self.xoff, self.yoff))]).to_file(self.out_path)

    def pixel2point(self, pxl):
        x,y = pxl
        posY = self.a * x + self.b * y + self.yoff
        posX = self.d * x + self.e * y + self.xoff
        #posX += (a/2)
        #posY += (a/2)
        return Point(posX, posY)

    def outputResult(self):
        # buffering fixes self intersecting geometries
        # I can't tell you why the rotation is required
        # if multipolygon get largest
        vector_footprint = affinity.rotate(Polygon(self.pnts).buffer(0), 180, (self.xoff, self.yoff))
        if vector_footprint.geom_type == 'MultiPolygon':
            vector_footprint = max(vector_footprint, key=lambda a: a.area)

        print("outputting...")
        geoDF = gpd.GeoDataFrame(pd.DataFrame(['p1'], columns=['geom']),
                                 crs=self.dst_crs,
                                 geometry=[vector_footprint])
        geoDF.to_file(self.out_path)
        if self.output_CAD:
            try:
                geoDF.to_file(self.out_path.replace(".shp", ".dxf"), driver='DXF')
            except Exception:
                pass
        self.result = geoDF

    def getStartingPixel(self):
        # Scan the array until a pixel containing data is found
        for x in range(0, self.arr.shape[0] - 1):  # this is wrong its y,x but confusing to change
            for y in range(0, self.arr.shape[1] - 1):
                if self.arr[x, y] != self.no_data:
                    starting_pixel = (x, y)
                    entry_pixel = (x, y-1)
                    return starting_pixel, entry_pixel

    def MooresBoundaryTrace(self):
        # moores algorithm based on:
        # http://www.imageprocessingplace.com/downloads_V3/root_downloads/tutorials/contour_tracing_Abeer_George_Ghuneim/moore.html
        moores_neighbs = [(0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1)]  # clockwise

        starting_pixel, entry_pixel = self.getStartingPixel()

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
            if check_x >= 0 and check_y >= 0 and check_x < self.arr.shape[0] and check_y < self.arr.shape[1] and self.arr[check_x][check_y] != self.no_data:
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
    raster_path = r"C:\dev\Raster Preparer and ML Vectoriser\tifs\Dublin\20210630_142444_right.tif"
    out_path = r"C:\dev\Raster Preparer and ML Vectoriser\tifs\polygonised.shp"

    RasterFootPrintExtractor(
        out_path=out_path,
        raster_path=raster_path
    )