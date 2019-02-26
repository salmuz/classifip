from classifip.evaluation.measures import u65, u80
from classifip.dataset.uci_data_set import export_data_set
from qda_common import __factory_model, generate_seeds
from sklearn.model_selection import KFold
from classifip.utils import create_logger
import numpy as np, pandas as pd, sys
from sklearn.model_selection import train_test_split

QPBB_PATH_SERVER = ['/home/lab/ycarranz/QuadProgBB', '/opt/cplex128/cplex/matlab/x86-64_linux']


def performance_accuracy_hold_out(in_path=None, model_type="ilda", ell_optimal=0.1, lib_path_server=None,
                                  seeds=None, DEBUG=False):
    assert os.path.exists(in_path), "Without training data, cannot performing cross hold-out accuracy"
    data = pd.read_csv(in_path)
    logger = create_logger("performance_accuracy_hold_out", True)
    logger.info('Training dataset (%s, %s, %s)', in_path, model_type, ell_optimal)
    X = data.iloc[:, :-1].values
    y = data.iloc[:, -1].tolist()
    seeds = generate_seeds(cv_n_fold) if seeds is None else seeds
    logger.info('Seeds used for accuracy %s', seeds)
    n_time = len(seeds)
    mean_u65, mean_u80 = 0, 0
    model = __factory_model(model_type, init_matlab=True, add_path_matlab=lib_path_server, DEBUG=DEBUG)
    for k in range(0, n_time):
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.4, random_state=seeds[k])
        model.learn(X=X_cv_train, y=y_cv_train, ell=ell_optimal)
        sum_u65, sum_u80 = 0, 0
        n_test, _ = X_test.shape
        for i, test in enumerate(X_test):
            evaluate, _ = lqa.evaluate(test)
            logger.debug("(testing, ell_current, prediction, ground-truth) (%s, %s, %s, %s)",
                         i, ell_optimal, evaluate, y_test[i])
            if y_test[i] in evaluate:
                sum_u65 += u65(evaluate)
                sum_u80 += u80(evaluate)
        logger.debug("Partial-kfold (%s, %s, %s, %s)", ell_current, k, sum_u65 / n_test, sum_u80 / n_test)
        mean_u65 += sum_u65 / n_test
        mean_u80 += sum_u80 / n_test
    mean_u65 = mean_u65 / n_time
    mean_u80 = mean_u80 / n_time
    logger.debug("Total-ell (%s, %s, %s, %s)", in_path, ell_optimal, mean_u65, mean_u80)


def performance_cv_accuracy_imprecise(in_path=None, model_type="ilda", ell_optimal=0.1,
                                      lib_path_server=None, cv_n_fold=10, seeds=None, DEBUG=False):
    assert os.path.exists(in_path), "Without training data, cannot performing cross validation accuracy"
    data = pd.read_csv(in_path)
    logger = create_logger("performance_cv_accuracy_imprecise", True)
    logger.info('Training dataset (%s, %s, %s)', in_path, model_type, ell_optimal)
    X = data.iloc[:, :-1].values
    y = np.array(data.iloc[:, -1].tolist())
    avg_u65, avg_u80 = 0, 0
    seeds = generate_seeds(cv_n_fold) if seeds is None else seeds
    logger.info('Seeds used for accuracy %s', seeds)
    model = __factory_model(model_type, init_matlab=True, add_path_matlab=lib_path_server, DEBUG=DEBUG)
    for time in range(cv_n_fold):
        kf = KFold(n_splits=cv_n_fold, random_state=seeds[time], shuffle=True)
        mean_u65, mean_u80 = 0, 0
        for idx_train, idx_test in kf.split(y):
            X_cv_train, y_cv_train = X[idx_train], y[idx_train]
            X_cv_test, y_cv_test = X[idx_test], y[idx_test]
            model.learn(X=X_cv_train, y=y_cv_train, ell=ell_optimal)
            sum_u65, sum_u80 = 0, 0
            n_test, _ = X_cv_test.shape
            for i, test in enumerate(X_cv_test):
                evaluate, _ = model.evaluate(test)
                logger.debug("(testing, ell_current, prediction, ground-truth) (%s, %s, %s, %s)",
                             i, ell_optimal, evaluate, y_cv_test[i])
                if y_cv_test[i] in evaluate:
                    sum_u65 += u65(evaluate)
                    sum_u80 += u80(evaluate)
            logger.debug("Partial-kfold (%s, %s, %s, %s)", ell_optimal, time, sum_u65 / n_test, sum_u80 / n_test)
            mean_u65 += sum_u65 / n_test
            mean_u80 += sum_u80 / n_test
        logger.info("Time, seed, u65, u80 (%s, %s, %s, %s)", time, seeds[time], mean_u65 / cv_n_fold,
                    mean_u80 / cv_n_fold)
        avg_u65 += mean_u65 / cv_n_fold
        avg_u80 += mean_u80 / cv_n_fold
    logger.debug("Total-ell (%s, %s, %s, %s)", in_path, ell_optimal, avg_u65 / cv_n_fold, avg_u80 / cv_n_fold)


in_path = sys.argv[1]
ell_optimal = float(sys.argv[2])
# QPBB_PATH_SERVER = []
performance_cv_accuracy_imprecise(in_path=in_path, ell_optimal=ell_optimal, model_type="ilda",
                                  lib_path_server=QPBB_PATH_SERVER)
