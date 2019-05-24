# -*- coding: utf-8 -*-

import math
import copy
import numpy as np
import pandas as pd


class GasOil(object):
    """Representing gas-oil two-phase properties

    Very similar code to WaterOil, but with some subtle details
    different for now warranting its own code (and no inheritance)

    krgend can be anchored both to (1-swl-sorg) and to (1-swl). Default is
    to anchor to (1-swl-sorg). If the krgendanchor argument is something
    else than the string 'sorg', it will be anchored to (1-swl).
    """

    def __init__(
        self,
        swirr=0,
        sgcr=0.05,
        h=0.01,
        swl=0.05,
        sorg=0.04,
        tag="",
        krgendanchor="sorg",
    ):
        self.h = h
        swl = max(swl, swirr)  # Can't allow swl < swirr, should we warn user?
        self.swl = swl
        self.swirr = swirr
        self.sorg = sorg
        self.sgcr = sgcr
        self.tag = tag
        if not 1 - sorg - swl > 0:
            raise Exception(
                "No saturation range left " + "after endpoints, check input"
            )
        if np.isclose(sorg, 0.0):
            krgendanchor = ""  # not meaningful to anchor to sorg if sorg is zero
        self.krgendanchor = krgendanchor
        sg = (
            [0]
            + [sgcr]
            + list(np.arange(sgcr + h, 1 - swl, h))
            + [1 - sorg - swl]
            + [1 - swl]
        )
        self.table = pd.DataFrame(sg, columns=["sg"])
        self.table["sgint"] = list(
            map(int, list(map(round, self.table["sg"] * SWINTEGERS)))
        )
        self.table.drop_duplicates("sgint", inplace=True)
        self.table.sort_values(by="sg", inplace=True)
        self.table.reset_index(inplace=True)
        self.table = self.table[["sg"]]
        self.table["sl"] = 1 - self.table["sg"]
        if krgendanchor == "sorg":
            self.table["sgn"] = (self.table.sg - sgcr) / (1 - swl - sgcr - sorg)
        else:
            self.table["sgn"] = (self.table.sg - sgcr) / (1 - swl - sgcr)
        self.table["son"] = (1 - self.table.sg - sorg - swl) / (1 - sorg - swl)
        self.sgcomment = "-- swirr=%g, sgcr=%g, swl=%g, sorg=%g\n" % (
            self.swirr,
            self.sgcr,
            self.swl,
            self.sorg,
        )
        self.krgcomment = ""
        self.krogcomment = ""
        self.pccomment = ""

    def resetsorg(self):
        """Recalculate sorg in case it has table data has been manipulated"""
        if "krog" in self.table.columns:
            self.sorg = (
                1 - self.swl - self.table[np.isclose(self.table.krog, 0.0)].min()["sg"]
            )
            self.sgcomment = "-- swirr=%g, sgcr=%g, swl=%g, sorg=%g\n" % (
                self.swirr,
                self.sgcr,
                self.swl,
                self.sorg,
            )

    def add_gasoil_fromtable(
        self,
        df,
        sgcolname="Sg",
        krgcolname="krg",
        krogcolname="krog",
        pccolname="pcog",
        krgcomment="",
        krogcomment="",
        pccomment="",
    ):
        """Interpolate relpermdata from a dataframe.

        The saturation range with endpoints must be set up beforehand,
        and must be compatible with the tabular input. The tabular
        input will be interpolated to the initialized Sg-table.
        IMPORTANT: Set sgcr and swl to sensible values.

        If you have krg and krog in different dataframes, call this
        function twice

        Calling function is responsible for checking if any data was
        actually added to the table.

        The dataframe input can be constructed using e.g. swof2csv functionality

        """
        from scipy.interpolate import PchipInterpolator

        if sgcolname not in df:
            raise Exception(
                sgcolname + " not found in dataframe, " + "can't read table data"
            )
        swlfrominput = 1 - df[sgcolname].max()
        if abs(swlfrominput - self.swl) < epsilon:
            print(
                "Warning: swl and 1-max(sg) from incoming table does not seem compatible"
            )
            print("         Do not trust the result near the endpoint.")
        if krgcolname in df:
            pchip = PchipInterpolator(
                df[sgcolname].astype(float), df[krgcolname].astype(float)
            )
            # Do not extrapolate this data. We will bfill and ffill afterwards
            self.table["krg"] = pchip(self.table.sg, extrapolate=False)
            self.table["krg"].fillna(method="ffill", inplace=True)
            self.table["krg"].fillna(method="bfill", inplace=True)
            self.krgcomment = "-- krg from tabular input" + krgcomment + "\n"
        if krogcolname in df:
            pchip = PchipInterpolator(
                df[sgcolname].astype(float), df[krogcolname].astype(float)
            )
            self.table["krog"] = pchip(self.table.sg, extrapolate=False)
            self.table["krog"].fillna(method="ffill", inplace=True)
            self.table["krog"].fillna(method="bfill", inplace=True)
            self.krogcomment = "-- krog from tabular input" + krogcomment + "\n"
        if pccolname in df:
            pchip = PchipInterpolator(
                df[sgcolname].astype(float), df[pccolname].astype(float)
            )
            self.table["pc"] = pchip(self.table.sg, extrapolate=False)
            self.pccomment = "-- pc from tabular input" + pccomment + "\n"

    def add_corey_gas(self, ng=2, krgend=1, krgmax=1):
        """ Add krg data through the Corey parametrization"""
        self.table["krg"] = krgend * self.table.sgn ** ng
        self.table.loc[self.table.sg <= self.sgcr, "krg"] = 0
        # Warning: code duplicated from add_LET_gas():
        if self.krgendanchor == "sorg":
            # Linear curve between krgendcanchor and 1-swl if krgend
            # is anchored to sorg
            tmp = pd.DataFrame(self.table[["sg"]])
            tmp["sgendnorm"] = (tmp["sg"] - (1 - (self.sorg + self.swl))) / (self.sorg)
            tmp["krg"] = tmp["sgendnorm"] * krgmax + (1 - tmp["sgendnorm"]) * krgend
            self.table.loc[
                self.table.sg >= (1 - (self.sorg + self.swl + epsilon)), "krg"
            ] = tmp.loc[tmp.sg >= (1 - (self.sorg + self.swl + epsilon)), "krg"]
        else:
            self.table.loc[
                self.table.sg > (1 - (self.swl + epsilon)), "krg"
            ] = krgend  # krgmax should not be used when we don't
            # anchor to sorg.
        self.krgcomment = "-- Corey krg, ng=%g, krgend=%g, krgmax=%g\n" % (
            ng,
            krgend,
            krgmax,
        )

    def add_corey_oil(self, nog=2, kroend=1):
        self.table["krog"] = kroend * self.table.son ** nog
        self.table.loc[self.table.sg > 1 - self.sorg - self.swl - epsilon, "krog"] = 0
        self.krogcomment = "-- Corey krog, nog=%g, kroend=%g\n" % (nog, kroend)

    def add_LET_gas(self, l=2, e=2, t=2, krgend=1, krgmax=1):
        self.table["krg"] = (
            krgend
            * self.table.sgn ** l
            / ((self.table.sgn ** l) + e * (1 - self.table.sgn) ** t)
        )
        self.table.loc[self.table.sg < self.sgcr - epsilon, "krg"] = 0
        if self.krgendanchor == "sorg":
            # Linear curve between krgendcanchor and 1-swl if krgend
            # is anchored to sorg
            tmp = pd.DataFrame(self.table[["sg"]])
            tmp["sgendnorm"] = (tmp["sg"] - (1 - (self.sorg + self.swl))) / (self.sorg)
            tmp["krg"] = tmp["sgendnorm"] * krgmax + (1 - tmp["sgendnorm"]) * krgend
            self.table.loc[
                self.table.sg >= (1 - (self.sorg + self.swl + epsilon)), "krg"
            ] = tmp.loc[tmp.sg >= (1 - (self.sorg + self.swl + epsilon)), "krg"]
        else:
            self.table.loc[
                self.table.sg > (1 - (self.swl + epsilon)), "krg"
            ] = krgend  # krgmax should not be used when we don't
            # anchor to sorg.
        self.krgcomment = "-- LET krg, l=%g, e=%g, t=%g, krgend=%g, krgmax=%g\n" % (
            l,
            e,
            t,
            krgend,
            krgmax,
        )

    def add_LET_oil(self, l=2, e=2, t=2, kroend=1):
        self.table["krog"] = (
            kroend
            * self.table.son ** l
            / ((self.table.son ** l) + e * (1 - self.table.son) ** t)
        )
        self.table.loc[self.table.sg > 1 - self.sorg - self.swl - epsilon, "krog"] = 0
        self.krogcomment = "-- LET krog, l=%g, e=%g, t=%g, kroend=%g\n" % (
            l,
            e,
            t,
            kroend,
        )

    def selfcheck(self):
        """Check validities of the data in the table.

        If you call SGOF/SLGOF, this function must not return False
        """
        error = False
        if not (self.table.sg.diff().dropna() > -epsilon).all():
            print("Error: sg data not strictly increasing")
            error = True
        if not (self.table.krg.diff().dropna() >= -epsilon).all():
            print("Error: krg data not monotonely decreaseing")
            error = True

        if (
            "krog" in self.table.columns
            and not (self.table.krog.diff().dropna() <= epsilon).all()
        ):
            print("Error: krog data not monotonely increasing")
            error = True
        if not np.isclose(min(self.table.krg), 0.0):
            print("Error: krg must start at zero")
            error = True
        if "pc" in self.table.columns and self.table.pc[0] > 0:
            if not (self.table.pc.diff().dropna() < epsilon).all():
                print("Error: pc data for gas-oil not strictly deceasing")
                error = True
        if "pc" in self.table.columns and np.isinf(self.table.pc.max()):
            print("Error: pc goes to infinity for gas-oil. ")
            error = True
        for col in list(set(["sg", "krg", "krog"]) & set(self.table.columns)):
            if not (
                (min(self.table[col]) >= -epsilon)
                and (max(self.table[col]) <= 1 + epsilon)
            ):
                print("Error: %s data should be contained in [0,1]" % col)
                error = True
        if error:
            return False
        else:
            return True

    def SGOF(self, header=True, dataincommentrow=True):
        if not self.selfcheck():
            return
        string = ""
        if "pc" not in self.table.columns:
            self.table["pc"] = 0
            self.pccomment = "-- Zero capillary pressure\n"
        if header:
            string += "SGOF\n"
        string += "-- " + self.tag + "\n"
        string += "-- Sg Krg Krog Pc\n"
        if dataincommentrow:
            string += self.sgcomment
            string += self.krgcomment
            string += self.krogcomment
            string += "-- krg = krog @ sw=%1.5f\n" % self.crosspoint()
            string += self.pccomment
        string += self.table[["sg", "krg", "krog", "pc"]].to_csv(
            sep=" ", float_format="%1.7f", header=None, index=False
        )
        string += "/\n"
        return string

    def SLGOF(self, header=True, dataincommentrow=True):
        if not self.selfcheck():
            return
        string = ""
        if "pc" not in self.table.columns:
            self.table["pc"] = 0
            self.pccomment = "-- Zero capillary pressure\n"
        if header:
            string += "SLGOF\n"
        string += "-- " + self.tag + "\n"
        string += "-- Sl Krg Krog Pc\n"
        if dataincommentrow:
            string += self.sgcomment
            string += self.krgcomment
            string += self.krogcomment
            string += "-- krg = krog @ sw=%1.5f\n" % self.crosspoint()
            string += self.pccomment
        string += (
            self.table[self.table.sg <= 1 - self.sorg - self.swl + epsilon]
            .sort_values("sl")[["sl", "krg", "krog", "pc"]]
            .to_csv(sep=" ", float_format="%1.7f", header=None, index=False)
        )
        string += "/\n"
        return string

    def SGFN(self, header=True, dataincommentrow=True):
        string = ""
        if "pc" not in self.table.columns:
            self.table["pc"] = 0
            self.pccomment = "-- Zero capillary pressure\n"
        if header:
            string += "SGFN\n"
        string += "-- " + self.tag + "\n"
        string += "-- Sg Krg Pc\n"
        if dataincommentrow:
            string += self.sgcomment
            string += self.krgcomment
            if "krog" in self.table.columns:
                string += "-- krg = krog @ sw=%1.5f\n" % self.crosspoint()
            string += self.pccomment
        string += self.table[["sg", "krg", "pc"]].to_csv(
            sep=" ", float_format="%1.7f", header=None, index=False
        )
        string += "/\n"
        return string

    def GOTABLE(self, header=True, dataincommentrow=True):
        """Return a string for a Nexus GOTABLE"""
        string = ""
        if "pc" not in self.table.columns:
            self.table["pc"] = 0
            self.pccomment = "-- Zero capillary pressure\n"
        if header:
            string += "GOTABLE\n"
            string += "SG KRG KROG PC\n"
        if dataincommentrow:
            string += self.sgcomment.replace("--", "!")
            string += self.krgcomment.replace("--", "!")
            string += self.krogcomment.replace("--", "!")
            string += "! krg = krog @ sw=%1.5f\n" % self.crosspoint()
            string += self.pccomment.replace("--", "!")
        string += self.table[["sg", "krg", "krog", "pc"]].to_csv(
            sep=" ", float_format="%1.7f", header=None, index=False
        )
        return string

    def crosspoint(self):
        """Locate and return the saturation point where krg = krog

        Accuracy of this crosspoint depends on the resolution chosen
        when initializing the saturation range (it uses linear
        interpolation to solve for the zero)

        Warning: Code duplication from WaterOil, with
        column names changed only
        """

        # Make a copy for calculations
        tmp = pd.DataFrame(self.table[["sg", "krg", "krog"]])
        tmp.loc[:, "krgminuskrog"] = tmp["krg"] - tmp["krog"]

        # Add a zero value for the difference column, and interpolate
        # the sw column to the zero value
        zerodf = pd.DataFrame(index=[len(tmp)], data={"krgminuskrog": 0.0})
        tmp = pd.concat([tmp, zerodf], sort=True)

        tmp.set_index("krgminuskrog", inplace=True)
        tmp.interpolate(method="slinear", inplace=True)

        return tmp[np.isclose(tmp.index, 0.0)].sg.values[0]

    def plotkrgkrog(
        self, ax=None, color="blue", alpha=1, label=None, linewidth=1, linestyle="-"
    ):
        """Plot krg and krog on a supplied matplotlib axis"""
        import matplotlib.pyplot as plt
        import matplotlib

        if not ax:
            matplotlib.style.use("ggplot")
            fig, useax = matplotlib.pyplot.subplots()
        else:
            useax = ax
        self.table.plot(
            ax=useax,
            x="sg",
            y="krg",
            c=color,
            alpha=alpha,
            legend=None,
            linewidth=linewidth,
            linestyle=linestyle,
        )
        self.table.plot(
            ax=useax,
            x="sg",
            y="krog",
            c=color,
            alpha=alpha,
            legend=None,
            linewidth=linewidth,
            linestyle=linestyle,
        )
        if not ax:
            plt.show()
