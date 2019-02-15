from sklearn.model_selection import train_test_split
from sklearn.model_selection import KFold
from classifip.evaluation.measures import u65, u80
from classifip.utils import create_logger
import sys, random, os, csv, numpy as np, pandas as pd
from qda_common import __factory_model, generate_seeds

## Server env:
# export LD_PRELOAD=/usr/local/MATLAB/R2018b/sys/os/glnxa64/libstdc++.so.6.0.22
QPBB_PATH_SERVER = ['/home/lab/ycarranz/QuadProgBB', '/opt/cplex128/cplex/matlab/x86-64_linux']

from multiprocessing import Process, Queue, cpu_count, JoinableQueue

class ManagerWorkers:

    def __init__(self, nb_process):
        self.workers = None
        self.tasks = Queue()
        self.results = Queue()
        self.qeTraining = [JoinableQueue() for i in range(nb_process)]
        self.NUMBER_OF_PROCESSES = cpu_count() if nb_process is None else nb_process

    def executeAsync(self, model_type, lib_path_server):
        print("starting %d workers" % self.NUMBER_OF_PROCESSES, flush=True)
        self.workers = []
        for i in range(self.NUMBER_OF_PROCESSES):
            p = Process(target=prediction,
                        args=(i, self.tasks, self.qeTraining[i], self.results, model_type, lib_path_server,))
            self.workers.append(p)

        for w in self.workers:
            w.start()

    def addNewTraining(self, **kwargs):
        for i in range(self.NUMBER_OF_PROCESSES):
            self.qeTraining[i].put(kwargs)

    def poisonPillTraining(self):
        for i in range(self.NUMBER_OF_PROCESSES): self.qeTraining[i].put(None)

    def joinTraining(self):
        for i in range(self.NUMBER_OF_PROCESSES): self.qeTraining[i].join()

    def addTask(self, task):
        self.tasks.put(task)

    def waitWorkers(self):
        for w in self.workers: w.join()

    def getResults(self):
        return self.results

    def poisonPillWorkers(self):
        for i in range(self.NUMBER_OF_PROCESSES): self.addTask(None)


def prediction(pid, tasks, queue, results, model_type, lib_path_server):
    model = __factory_model(model_type, init_matlab=True, add_path_matlab=lib_path_server, DEBUG=True)
    while True:
        training = queue.get()
        if training is None: break
        model.learn(**training)
        sum80, sum65 = 0, 0
        while True:
            task = tasks.get()
            if task is None: break
            evaluate, _ = model.evaluate(task['X_test'])
            print("(pid, prediction, ground-truth) ", pid, evaluate, task, flush=True)
            if task['y_test'] in evaluate:
                sum65 += u65(evaluate)
                sum80 += u80(evaluate)
        queue.task_done()
        results.put(dict({'u65': sum65, 'u80': sum80}))
    print("Worker PID finished", pid, flush=True)

def performance_cv_accuracy_imprecise(in_path=None, model_type="ilda", ell_optimal=0.1, nb_process=2,
                                      lib_path_server=None, cv_n_fold=10, seeds=None):
    data = export_data_set('iris.data') if in_path is None else pd.read_csv(in_path)
    logger = create_logger("computing_best_imprecise_mean", True)
    logger.info('Training dataset %s', in_path)
    X = data.iloc[:, :-1].values
    y = np.array(data.iloc[:, -1].tolist())
    avg_u65, avg_u80 = 0, 0
    seeds = generate_seeds(cv_n_fold) if seeds is None else seeds
    logger.info('Seeds used for accuracy %s', seeds)
    manager = ManagerWorkers(nb_process=nb_process)
    manager.executeAsync(model_type, lib_path_server)
    for time in range(cv_n_fold):
        kf = KFold(n_splits=cv_n_fold, random_state=seeds[time], shuffle=True)
        mean_u65, mean_u80 = 0, 0
        for idx_train, idx_test in kf.split(y):
            logger.info("Splits train %s",  idx_train)
            logger.info("Splits test %s", idx_test)
            X_cv_train, y_cv_train = X[idx_train], y[idx_train]
            X_cv_test, y_cv_test = X[idx_test], y[idx_test]
            n_test = len(idx_test)

            manager.addNewTraining(X=X_cv_train, y=y_cv_train, ell=ell_optimal)
            for i, test in enumerate(X_cv_test): manager.addTask({'X_test': test, 'y_test': y_cv_test[i]})
            manager.poisonPillWorkers()

            manager.joinTraining()  # wait all process for computing results
            shared_results = manager.getResults()
            shared_results.put('STOP')  ## stop loop queue
            for utility in iter(shared_results.get, 'STOP'):
                mean_u65 += utility['u65'] / n_test
                mean_u80 += utility['u80'] / n_test
            logger.debug("Partial-kfold (%s, %s, %s, %s)", ell_optimal, time, mean_u65, mean_u80)
        logger.info("Time, seed, u65, u80 (%s, %s, %s, %s)", time, seeds[time],
                    mean_u65 / cv_n_fold, mean_u80 / cv_n_fold)
        avg_u65 += mean_u65 / cv_n_fold
        avg_u80 += mean_u80 / cv_n_fold
    logger.debug("total-ell (%s, %s, %s, %s)", in_path, ell_optimal, avg_u65 / cv_n_fold, avg_u80 / cv_n_fold)



def computing_best_imprecise_mean(in_path=None, out_path=None, cv_nfold=10, model_type="ieda",
                                  from_ell=0.1, to_ell=1.0, by_ell=0.1, seed=None, lib_path_server=None,
                                  nb_process=2):
    assert os.path.exists(in_path), "Without training data, not testing"
    assert os.path.exists(out_path), "File for putting results does not exist"

    logger = create_logger("computing_best_imprecise_mean", True)
    logger.info('Training dataset %s', in_path)
    data = pd.read_csv(in_path)  # , header=None)
    X = data.iloc[:, :-1].values
    y = np.array(data.iloc[:, -1].tolist())

    ell_u65, ell_u80 = dict(), dict()
    seed = random.randrange(pow(2, 30)) if seed is None else seed
    logger.debug("MODEL: %s, SEED: %s", model_type, seed)
    kf = KFold(n_splits=cv_nfold, random_state=None, shuffle=True)
    splits = list([])
    for idx_train, idx_test in kf.split(y):
        splits.append((idx_train, idx_test))
        logger.info("Splits %s train %s", len(splits), idx_train)
        logger.info("Splits %s test %s", len(splits), idx_test)

    # Create a CSV file for saving results
    file_csv = open(out_path, 'a')
    writer = csv.writer(file_csv)
    manager = ManagerWorkers(nb_process=nb_process)
    manager.executeAsync(model_type, lib_path_server)
    for ell_current in np.arange(from_ell, to_ell, by_ell):
        ell_u65[ell_current], ell_u80[ell_current] = 0, 0
        logger.info("ELL_CURRENT %s", ell_current)
        for idx_train, idx_test in splits:
            logger.info("Splits train %s", idx_train)
            logger.info("Splits test %s", idx_test)
            X_cv_train, y_cv_train = X[idx_train], y[idx_train]
            X_cv_test, y_cv_test = X[idx_test], y[idx_test]
            n_test = len(idx_test)

            manager.addNewTraining(X=X_cv_train, y=y_cv_train, ell=ell_current)
            for i, test in enumerate(X_cv_test): manager.addTask({'X_test': test, 'y_test': y_cv_test[i]})
            manager.poisonPillWorkers()

            manager.joinTraining() # wait all process for computing results
            shared_results = manager.getResults()
            shared_results.put('STOP')  ## stop loop queue
            for utility in iter(shared_results.get, 'STOP'):
                ell_u65[ell_current] += utility['u65'] / n_test
                ell_u80[ell_current] += utility['u80'] / n_test
            logger.info("Partial-kfold (%s, %s, %s)", ell_current, ell_u65[ell_current], ell_u80[ell_current])

        ell_u65[ell_current] = ell_u65[ell_current] / cv_nfold
        ell_u80[ell_current] = ell_u80[ell_current] / cv_nfold
        writer.writerow([ell_current, ell_u65[ell_current], ell_u80[ell_current]])
        file_csv.flush()
        logger.debug("Partial-ell (%s, %s, %s)", ell_current, ell_u65, ell_u80)
    manager.poisonPillTraining()
    file_csv.close()
    logger.debug("Total-ell %s %s %s", in_path, ell_u65, ell_u80)


in_path = sys.argv[1]
out_path = sys.argv[2]
# QPBB_PATH_SERVER = []  # executed in host
computing_best_imprecise_mean(in_path=in_path, out_path=out_path, model_type="ilda",
                             from_ell=0.01, to_ell=5, by_ell=0.01,
                             lib_path_server=QPBB_PATH_SERVER, nb_process=3)

# in_path = sys.argv[1]
# ell_optimal = float(sys.argv[2])
# QPBB_PATH_SERVER = []  # executed in host
# performance_cv_accuracy_imprecise(in_path=in_path, ell_optimal=ell_optimal, model_type="ilda",
#                                   lib_path_server=QPBB_PATH_SERVER, nb_process=1)
