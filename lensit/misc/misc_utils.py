# Convenience functions :
from __future__ import print_function
import sys
import time

import numpy as np
import os
import hashlib
from lensit.pbs import pbs

def camb_clfile(fname, lmax=None):
    """CAMB spectra (lenspotentialCls, lensedCls or tensCls types) returned as a dict of numpy arrays.

    Args:
        fname (str): path to CAMB output file
        lmax (int, optional): outputs cls truncated at this multipole.

    """
    cols = np.loadtxt(fname).transpose()
    ell = np.int_(cols[0])
    if lmax is None: lmax = ell[-1]
    assert ell[-1] >= lmax, (ell[-1], lmax)
    cls = {k : np.zeros(lmax + 1, dtype=float) for k in ['tt', 'ee', 'bb', 'te']}
    w = ell * (ell + 1) / (2. * np.pi)  # weights in output file
    idc = np.where(ell <= lmax) if lmax is not None else np.arange(len(ell), dtype=int)
    for i, k in enumerate(['tt', 'ee', 'bb', 'te']):
        cls[k][ell[idc]] = cols[i + 1][idc] / w[idc]
    if len(cols) > 5:
        wpp = lambda ell : ell ** 2 * (ell + 1) ** 2 / (2. * np.pi)
        wptpe = lambda ell : np.sqrt(ell.astype(float) ** 3 * (ell + 1.) ** 3) / (2. * np.pi)
        for i, k in enumerate(['pp', 'pt', 'pe']):
            cls[k] = np.zeros(lmax + 1, dtype=float)
        cls['pp'][ell[idc]] = cols[5][idc] / wpp(ell[idc])
        cls['pt'][ell[idc]] = cols[6][idc] / wptpe(ell[idc])
        cls['pe'][ell[idc]] = cols[7][idc] / wptpe(ell[idc])
    return cls

def cls_hash(cls, lmax=None, astype=np.float32):
    if lmax is None:
        arr = np.concatenate([cls[k] for k in sorted(cls.keys())])
    else:
        arr = np.concatenate([(cls[k])[:lmax + 1] for k in sorted(cls.keys())])
    return hashlib.sha1(np.copy(arr.astype(astype), order='C')).hexdigest()

def npy_hash(npy_array, astype=np.float32):
    return hashlib.sha1(np.copy(npy_array.astype(astype), order='C')).hexdigest()

class timer:
    def __init__(self, verbose, prefix='', suffix=''):
        self.t0 = time.time()
        self.ti = np.copy(self.t0)
        self.verbose = verbose
        self.prefix = prefix
        self.suffix = suffix

    def checkpoint(self, msg):
        dt = time.time() - self.t0
        self.t0 = time.time()

        if self.verbose:
            dh = np.floor(dt / 3600.)
            dm = np.floor(np.mod(dt, 3600.) / 60.)
            ds = np.floor(np.mod(dt, 60))
            dhi = np.floor((self.t0 - self.ti) / 3600.)
            dmi = np.floor(np.mod((self.t0 - self.ti), 3600.) / 60.)
            dsi = np.floor(np.mod((self.t0 - self.ti), 60))
            sys.stdout.write("\r  %s   [" % self.prefix + ('%02d:%02d:%02d' % (dh, dm, ds)) + "] "
                             + " (total [" + (
                                 '%02d:%02d:%02d' % (dhi, dmi, dsi)) + "]) " + msg + ' %s \n' % self.suffix)


def read_params(paramfile):
    """
    Reads a parameter file with lines of the form key = value as a dictionary
    """
    assert os.path.exists(paramfile), paramfile
    params = {}
    with open(paramfile) as f:
        for line in f:
            (key, equal, val) = line.split()
            params[key] = val
    return params

def enumerate_progress(list, label=''):
    # Taken boldly from Duncan Hanson lpipe :
    #  e.g. : for i,v in enumerate_progress(list,label = 'calculating...')
    if pbs.size == 1 or pbs.rank == 0:
        t0 = time.time()
        ni = len(list)
        for i, v in enumerate(list):
            yield i, v
            ppct = int(100. * (i - 1) / ni)
            cpct = int(100. * (i + 0) / ni)
            if cpct > ppct:
                dt = time.time() - t0
                dh = np.floor(dt / 3600.)
                dm = np.floor(np.mod(dt, 3600.) / 60.)
                ds = np.floor(np.mod(dt, 60))
                sys.stdout.write("\r [" + ('%02d:%02d:%02d' % (dh, dm, ds)) + "] " +
                                 label + " " + int(10. * cpct / 100) * "-" + "> " + ("%02d" % cpct) + r"%")
                sys.stdout.flush()
        sys.stdout.write("\n");
        sys.stdout.flush()
    else:
        for i, v in enumerate(list):
            yield i, v


def IsPowerOfTwo(i):
    """
        Returns true if all entries of i are powers of two.
        False otherwise.
    """
    return (i & (i - 1)) == 0 and i != 0


def Log2ofPowerof2(shape):
    """
    Returns powers of two exponent for each element of shape
    """
    # There must be a better way, such as the first non zero byte.
    res = np.array(shape)
    for i in range(res.size):
        n = shape[i]
        assert (IsPowerOfTwo(n)), "Invalid input"
        ix = 0
        while n > 1:
            n /= 2
            ix += 1
        res[i] = ix
    return res


def int_tabulated(x, y, **kwargs):
    # Emulates IDL int_tabulated fct for the moment with scipy.integrate.sims
    from scipy.integrate import simps
    return simps(y, x=x, **kwargs)


class stats:
    """
    Simple minded routines for means and averages of sims .
    Calculates means as 1/N sum()
    and Cov as 1/(N-1)sum(x - mean)(x - mean)^t
    """

    def __init__(self, size, xcoord=None, do_cov=True, dtype=float):
        self.N = 0  # number of samples
        self.size = size  # dim of data vector
        self.sum = np.zeros(self.size, dtype=dtype)  # sum_i x_i
        self.do_cov = do_cov
        if self.do_cov:
            self.mom = np.zeros((self.size, self.size))  # sum_i x_ix_i^t
        self.xcoord = xcoord

    def add(self, v):
        assert (v.shape == (self.size,)), "input not understood"
        self.sum += v
        if self.do_cov:
            self.mom += np.outer(v, v)
        self.N += 1

    def mean(self):
        assert (self.N > 0)
        return self.sum / self.N

    def cov(self):
        """
        1/(N-1) sum_i = 1^N (X_i - bX)(X_i - bX)
        = Mom / (N-1) + N/(N-1) bX bX^t - 2 N / (N-1) bX bX^t
        = Mom / (N-1) - N/(N-1) bX bX^t
        """
        assert (self.N > 0)
        assert self.do_cov
        if self.N == 1: return np.zeros((self.size, self.size))
        mean = self.mean()
        return self.mom / (self.N - 1.) - np.outer(mean, mean * (self.N / (self.N - 1.)))

    def sigmas(self):
        return np.sqrt(np.diagonal(self.cov()))

    def corrcoeffs(self):
        assert self.do_cov
        sigmas = self.sigmas()
        return self.cov() / np.outer(sigmas, sigmas)

    def sigmas_on_mean(self):
        assert (self.N > 0)
        return self.sigmas() / np.sqrt(self.N)

    def inverse(self, bias_p=None):  # inverse cov, using unbiasing a factor following G. statistics
        assert (self.N > self.size), "Non invertible cov.matrix"
        if bias_p is None: bias_p = (self.N - self.size - 2.) / (self.N - 1)
        return bias_p * np.linalg.inv(self.cov())

    def get_chisq(self, data):  # Returns (data -mean)Sig^{-1}(data-mean)
        assert (data.size == self.size), "incompatible input"
        dx = data - self.mean()
        return np.sum(np.outer(dx, dx) * self.inverse())

    def get_chisq_pte(self, data):  # probability to exceed, or survival function
        from scipy.stats import chi2
        return chi2.sf(self.get_chisq(data), self.N - 1)  # 'survival function' of chisq distribution with N -1 dof

    def rebin_that_nooverlap(self, orig_coord, lmins, lmaxs, weights=None):
        # Returns a new stat instance rebinning with non-overlapping weights
        # >= a gauche, <= a droite.
        assert (orig_coord.size == self.size), "Incompatible input"
        assert (lmins.size == lmaxs.size), "Incompatible input"
        assert (np.all(np.diff(np.array(lmins)) > 0.)), "This only for non overlapping bins."
        assert (np.all(np.diff(np.array(lmaxs)) > 0.)), "This only for non overlapping bins."
        assert (np.all(lmaxs - lmins) > 0.), "This only for non overlapping bins."

        if weights is None: weights = np.ones(self.size)
        assert (weights.size == self.size), "incompatible input"
        newsize = len(lmaxs)
        assert (self.size > newsize), "Incompatible dimensions"
        Tmat = np.zeros((newsize, self.size))
        newsum = np.zeros(newsize)
        for k, lmin, lmax in zip(np.arange(newsize), lmins, lmaxs):
            idc = np.where((orig_coord >= lmin) & (orig_coord <= lmax))
            if len(idc) > 0:
                norm = np.sum(weights[idc])
                Tmat[k, idc] = weights[idc] / norm
                newsum[k] = np.sum(weights[idc] * self.sum[idc]) / norm

        newmom = np.dot(np.dot(Tmat, self.mom), Tmat.transpose())  # New mom. matrix is T M T^T
        newstats = stats(newsize, xcoord=0.5 * (lmins[0:len(lmins) - 1] + lmax[1:]))
        # Resets the stats things
        newstats.mom = newmom
        newstats.sum = newsum
        newstats.N = self.N
        return newstats


def binned(Cl, nzell, bins_l, bins_u, w=lambda ell: np.ones(len(ell), dtype=float), return_err=False, meanorsum='mean'):
    """
    nzell: ells to consider. Use this e.g. to exclude modes with zero counts in flat sky maps.
    """
    assert meanorsum in ['mean', 'sum']
    if meanorsum == 'sum': assert not return_err, 'not implemented'
    sumfunc = np.mean if meanorsum == 'mean' else np.sum
    ellmax = np.max(bins_u)
    ell = np.arange(ellmax + 1, dtype=int)
    Nbins = bins_l.size
    assert (Nbins == bins_u.size), "incompatible limits"
    # enlarge array if needed
    ret = np.zeros(Nbins)
    arr = w(ell)
    err = np.zeros(Nbins)
    # This should work for ist.cl and arrays
    arr[0: min(len(Cl), ellmax + 1)] *= Cl[0:min(len(Cl), ellmax + 1)]
    for i in range(Nbins):
        if (bins_u[i] < arr.size) and (len(arr[bins_l[i]:bins_u[i] + 1]) >= 1):
            ii = np.where((nzell >= bins_l[i]) & (nzell <= bins_u[i]))
            ret[i] = sumfunc(arr[nzell[ii]])
            err[i] = np.std(arr[nzell[ii]]) / np.sqrt(max(1, len(ii[0])))
    if not return_err:
        return ret
    return ret, err

class binner():
    def __init__(self, bins_l, bins_r):
        """
        Binning routines. Left and right inclusive.
        For most general situation
        :param bins_l: left edges (inclusive)
        :param bins_r: right edges (inclusive)
        """
        assert (len(bins_l) == len(bins_r)), "inconsistent inputs"
        assert (np.all(bins_r - bins_l > 0.)), "inconsistent input"
        self.bins_l = np.array(bins_l)
        self.bins_r = np.array(bins_r)

    def Nbins(self):
        return len(self.bins_l)

    def bin_centers(self):
        return 0.5 * self.bins_l + 0.5 * self.bins_r

    def bin_that(self, x, y, weights=None, return_err=False):
        ret = np.zeros(self.Nbins())
        if weights is None: weights = np.ones(len(x), dtype=float)
        assert (len(x) == len(y) and len(x) == len(weights)), "inconsistent inputs"
        err = np.zeros(self.Nbins())
        for i, bin_l, bin_r in zip(range(self.Nbins()), self.bins_l, self.bins_r):
            idc = np.array(np.where((x >= bin_l) & (x <= bin_r)))
            if idc.size > 0.:
                ret[i] = np.sum(y[idc] * weights[idc]) / idc.size
                err[i] = np.std(y[idc] * weights[idc]) / np.sqrt(idc.size)
        if not return_err:
            return ret
        else:
            return ret, err


def rfft2_sum(rfft_map):
    """ Implementation of \sum_k map_k when using rfft arrays : (for odd number of points set only [:,0]) """
    assert len(rfft_map.shape) == 2
    if rfft_map.shape[1] % 2 == 0:
        return 2 * np.sum(rfft_map) - np.sum(rfft_map[:, [-1, 0]])
    else:
        2 * np.sum(rfft_map) - np.sum(rfft_map[:, 0])


def PartialDerivativePeriodic(arr, axis, h=1., rule='4pts'):
    """
    Returns the partial derivative of the arr along axis 'axis',
    following a 2pts or 4pts rule, reinventing the wheel.
    Uses periodic boundary conditions.
    """
    if rule == '4pts':  # O(h**4) rule
        idc = [-2, -1, 1, 2]
        weights = np.array((-1., 8., -8., 1.)) / (12. * h)
    elif rule == '2pts':  # O(h**2) rule
        idc = [-1, 1]  # np.rolling by one means g(x) =  f(x -1)
        weights = np.array((1., -1)) / (2. * h)
    else:
        idc = 0
        weights = 0
        assert 0, rule + " not implemented"

    grad = np.roll(arr, idc[0], axis=axis) * weights[0]
    for i, w in zip(idc[1:], weights[1:]): grad += np.roll(arr, i, axis=axis) * w
    return grad


def outerproducts(vs):
    """
    vs is a list of 1d numpy arrays, not necessarily of the same size.
    Return a matrix A_i1_i2..i_ndim = vi1_vi2_..v_indim.
    Use np.outer recursively on flattened arrays.
    """

    # check input and infer new shape  :
    assert (isinstance(vs, list)), "Want list of 1d arrays"
    ndim = len(vs)
    if ndim == 1: return vs[0]
    shape = ()
    for i in range(ndim):
        assert (vs[i].ndim == 1), "Want list of 1d arrays"
        shape += (vs[i].size,)

    B = vs[ndim - 1]

    for i in range(1, ndim): B = np.outer(vs[ndim - 1 - i], B).flatten()
    return B.reshape(shape)


def square_pixwin_map(shape):
    """
    pixel window function of square top hat for any dimension.
    k*lcell / 2
    """

    vs = []
    for ax in range(len(shape)):
        lcell_ka = 0.5 * Freq(np.arange(shape[ax]), shape[ax]) * (2. * np.pi / shape[ax])
        vs.append(np.insert(np.sin(lcell_ka[1:]) / lcell_ka[1:], 0, 1.))
    return outerproducts(vs)


def Freq(i, N):
    """
     Outputs the absolute integers frequencies [0,1,...,N/2,N/2-1,...,1]
     in numpy fft convention as integer i runs from 0 to N-1.
     Inputs can be numpy arrays e.g. i (i1,i2,i3) with N (N1,N2,N3)
                                  or i (i1,i2,...) with N
     Both inputs must be integers.
     All entries of N must be even.
    """
    assert (np.all(N % 2 == 0)), "This routine only for even numbers of points"
    return i - 2 * (i >= (N / 2)) * (i % (N / 2))

# --------------------------
# Some simple-minded utils for verbose mode on :
# --------------------------

def LevelUp(verbose):
    return verbose + (verbose > 0)


def Offset(verbose):
    offset = ' '
    for i in range(verbose - 1):
        offset += '  .../'
    return offset


def PrtAndRstTime(verbose, t0):
    print(Offset(verbose) + "--- %0.2fs ---" % (time.time() - t0))
    return time.time()


def PrtMsg(msg, verbose):
    print(Offset(verbose) + msg)
