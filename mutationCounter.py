#!/usr/bin/env python

#############################################################################
#   mutationCounter.py
#   2015 James A. Stapleton, Justin R. Klesmith
#
#   This program takes short reads from shotgun sequencing of mutant
#       libraries and creates FASTQ files compatible with ENRICH.
#
#
#############################################################################

import argparse
import subprocess
import os
import itertools
from Bio.SeqIO.QualityIO import FastqGeneralIterator
from Bio.Emboss.Applications import WaterCommandline


def main(infile_F, infile_R):

    fakeFASTQ = ''
    notAligned = 0
    wrongLength = 0

    # open file containing wild-type sequence and pull it out as a string
    wt = wtParser()

    # take trimmed paired-end FASTQ files as input
    # run FLASH to combine overlapping read pairs
    # or remove this line and add to shell script
    subprocess.call(["flash", "-M", "140", "-t", "1", infile_F, infile_R])

    # merged read pairs
    with open("fakeFASTQ.fastq", "w") as fakeFASTQ:
        with open("out.extendedFrags.fastq", "rU") as merged:
            for (title, seq, qual) in FastqGeneralIterator(merged):
                index1, index2, notAligned, seq = align_and_index(seq, notAligned)
                if index1 and index2:
                    fakeSeq = buildFakeSeq(seq, 0, wt, index1, index2, 0, 0)
                    if len(fakeSeq) != len(wt):
                        wrongLength += 1
                        continue
                    fakeFASTQwriter(fakeSeq, title, fakeFASTQ)

        # unmerged (non-overlapping) read pairs
        with open("out.notCombined_1.fastq", 'rU') as unmerged_F:
            with open("out.notCombined_2.fastq", 'rU') as unmerged_R:
                f_iter = FastqGeneralIterator(unmerged_F)
                r_iter = FastqGeneralIterator(unmerged_R)
                for (title, seq, qual), (title_R, seq_R, qual_R) in itertools.izip(f_iter, r_iter):
                    index1, index2, notAligned, seq = align_and_index(seq, notAligned)
                    if index1 and index2:
                        index3, index4, notAligned, seq_R = align_and_index(seq_R, notAligned)
                        if index3 and index4:
                            fakeSeq = buildFakeSeq(seq, seq_R, wt, index1, index2, index3, index4)
                            if len(fakeSeq) != len(wt):
                                wrongLength += 1
                                continue
                            fakeFASTQwriter(fakeSeq, title, fakeFASTQ)

    print notAligned, wrongLength

    return 0


######## Function definitions ##############


def revcomp(seq):
    COMPLEMENT_DICT = {'A': 'T', 'G': 'C', 'T': 'A', 'C': 'G', 'N': 'N'}
    rc = ''.join([COMPLEMENT_DICT[base] for base in seq])[::-1]
    return rc


def buildFakeSeq(seq_F, seq_R_rc, wt, index1, index2, index3, index4):
    '''Construct a FASTQ compatible with Enrich'''
    if seq_R_rc:
        if index1 < index3:
            if index2 > index3 - 1:
                index2 = index3 - 1
            fakeRead = wt[:index1 - 1] + seq_F + wt[index2:index3 - 1] + seq_R_rc + wt[index4:]
        else:
            if index4 > index1 - 1:
                index4 = index1 -1
            fakeRead = wt[:index3 - 1] + seq_F + wt[index4:index1 - 1] + seq_R_rc + wt[index2:]
    else:
        fakeRead = wt[:index1-1] + seq_F + wt[index2:]
    return fakeRead


def indexFinder(infile):
    ''' Searches output file from water for alignment position indexes '''
    with open(infile, 'rU') as waterdata:
        for line in waterdata:
            if len(line.split()) > 1:
                if line.split()[1] == 'al_start:':
                    start = int(line.split()[2])
                if line.split()[1] == 'al_stop:':
                    stop = int(line.split()[2])
                    break
    return start, stop


def Ntest(seq):
    "trim sequences with N's"
    if seq[0] == 'N':
        seq = seq[1:]
    Ntest = 0
    for i, ch in enumerate(seq):
        if ch == 'N':
            Ntest = 1
            break
    if Ntest == 1:
        seq = seq[:i-1]
    return seq


def runWater():
    if os.path.isfile('water.txt'):
        os.remove('water.txt')
    water_cline = WaterCommandline(asequence="wt.fasta", bsequence="read.fasta", gapopen=10, gapextend=0.5, outfile="water.txt", aformat='markx10')
    stdout, stderr = water_cline()
    return 0


def alignChecker():
    with open("water.txt", "rU") as waterfile:
        for line in waterfile:
            if len(line.split()) > 1:
                if line.split()[1] == 'Identity:':
                    identity = line.split()[3]
                    identity = identity[1:4]
                    if float(identity) > 90:
                        return 0
    return 1


def wtParser():
    with open('wt.fasta', 'rU') as wildtype:
        wildtype = wildtype.read()
    if wildtype[0] == ">":
        wildtype = wildtype.split('\n', 1)[1]
    wt = ''.join([line.strip() for line in wildtype.split('\n')])
    return wt


def align_and_index(seq, notAligned):
    # trim sequences with N's
    seq = Ntest(seq)
    # create a file to write each read to as fasta
    with open("read.fasta", "w") as readsfile:
        readsfile.write(">read\n")
        readsfile.write(seq)
    # generate water command line and call it
    runWater()
    # Check whether the read was in the right orientation
    #   If the Identity score of the alignment is low,
    #   take the revcomp and try aligning again
    alignCheck = alignChecker()
    if alignCheck:
        with open("read.fasta", "w") as readfile:
            readfile.write(">read\n")
            seq = revcomp(seq)
            readfile.write(seq)
        runWater()
        alignCheck = alignChecker()
    if alignCheck:
        notAligned += 1
        index1 = 0
        index2 = 0
    else:
        # find wt positions where the read aligns
        index1, index2 = indexFinder('water.txt')
    return index1, index2, notAligned, seq


def fakeFASTQwriter(fakeSeq, title, handle):
    handle.write('@' + title + '\n')
    handle.write(fakeSeq + '\n')
    handle.write('+\n')
    fakeQual = ''.join(['A' for ch in fakeSeq])
    handle.write(fakeQual + '\n')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('infile_F')
    parser.add_argument('infile_R')
    args = parser.parse_args()
    main(args.infile_F, args.infile_R)
