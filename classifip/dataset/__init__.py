from . import arff
from . import uci_data_set
from Orange.data import Table as OTable
from Orange.preprocess import Discretize as Disc
#from Orange.data.discretization import DiscretizeTable as DiscTable

def discretize_ent(infilename,outfilename):
    """
    Discretize features of data sets according to the MDL method proposed by
    [#fayyad1993]_. Necessitate Orange Python module to perform the
    discretization. Only discretize all continuous features of classification datasets.
    
    :param infilename: name of the input file (expecting an arff file)
    :type infilename: string
    :param outfilename: name of the output file
    :type outfilename: string
    """
    
    data = OTable(infilename)
    disc=Disc()
    disc.method=EntropyMDL()

    data_ent = disc(data)

    # Manipulation of the discretized data
    for attr in data_ent.domain.attributes :
        #Reset renamed attributes name to original ones
        if (attr.name[0:2] == "D_"):
            attr.name = attr.name[2:]
            attr.values = [val.replace(',',";") for val in attr.values]
    
    # save the discretized data
    data_ent.save(outfilename)