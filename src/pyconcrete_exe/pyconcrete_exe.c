#include <Python.h>
#include <stdlib.h>
#include "pyconcrete.h"
#include "pyconcrete_module.h"
#include "pyconcrete_py_src.h"

#define STRINGIFY(x) #x
#define TOSTRING(x) STRINGIFY(x)

#define RET_OK 0
#define RET_FAIL 1

#if PY_MAJOR_VERSION >= 3 && PY_MINOR_VERSION <=7
    #define SETUP_ARGV_BY_LEGACY
#else
    #define SETUP_ARGV_BY_PYCONFIG
#endif

// WIN32 platform use wmain, all string related functions should change to wchar_t version
#ifdef WIN32
    #define _CHAR                                       wchar_t
    #define _T(s)                                       L##s
    #define _fopen                                      _wfopen
    #define _strncmp                                    wcsncmp
    #define _strlen                                     wcslen
    #define _PyConfig_SetArgv                           PyConfig_SetArgv
    #define _PyConfig_SetString                         PyConfig_SetString
    #define _PyUnicode_FromStringAndSize                PyUnicode_FromWideChar
#else
    #define _CHAR                                       char
    #define _T(s)                                       s
    #define _fopen                                      fopen
    #define _strncmp                                    strncmp
    #define _strlen                                     strlen
    #define _PyConfig_SetArgv                           PyConfig_SetBytesArgv
    #define _PyConfig_SetString                         PyConfig_SetBytesString
    #define _PyUnicode_FromStringAndSize                PyUnicode_FromStringAndSize
#endif


int createAndInitPyconcreteModule();
int runFile(const _CHAR* filepath);
int prependSysPath0(const _CHAR* script_path);
int isZipFile(const _CHAR* filepath);
int prependSysPath0ForPyz(const _CHAR* pyz_path);
int runPyzFile(const _CHAR* filepath);
void initPython(int argc, _CHAR *argv[]);
PyObject* getFullPath(const _CHAR* filepath);


#ifdef WIN32
int wmain(int argc, wchar_t *argv[])
#else
int main(int argc, char *argv[])
#endif
{
    int ret = RET_OK;

    // PyImport_AppendInittab must set up before Py_Initialize
    if (PyImport_AppendInittab("_pyconcrete", PyInit__pyconcrete) == -1)
    {
        fprintf(stderr, "Error, can't load embedded _pyconcrete correctly!\n");
        return RET_FAIL;
    }

    initPython(argc, argv);
    Py_Initialize();
    PyGILState_Ensure();

    if (createAndInitPyconcreteModule() == -1)
    {
        fprintf(stderr, "Error: Failed to import embedded pyconcrete.\n");
        Py_Finalize();
        return RET_FAIL;
    }

    if(argc >= 2)
    {
        if(argc == 2 && (_strncmp(argv[1], _T("-v"), 3)==0 || _strncmp(argv[1], _T("--version"), 10)==0))
        {
            printf("pyconcrete %s [Python %s]\n", TOSTRING(PYCONCRETE_VERSION), TOSTRING(PY_VERSION));  // defined by build-backend
        }
        else
        {
#if defined(SETUP_ARGV_BY_LEGACY)
    #if defined(WIN32)
            PySys_SetArgv(argc-1, argv+1);
    #else
            int i, len;
            wchar_t** argv_ex = NULL;
            argv_ex = (wchar_t**) malloc(sizeof(wchar_t*) * argc);
            // setup
            for(i=0 ; i<argc ; ++i)
            {
                len = mbstowcs(NULL, argv[i], 0);
                argv_ex[i] = (wchar_t*) malloc(sizeof(wchar_t) * (len+1));
                mbstowcs(argv_ex[i], argv[i], len);
                argv_ex[i][len] = 0;
            }

            // set argv
            PySys_SetArgv(argc-1, argv_ex+1);

            // release
            for(i=0 ; i<argc ; ++i)
            {
                free(argv_ex[i]);
            }
    #endif
#endif // SETUP_ARGV_BY_LEGACY

            if (isZipFile(argv[1]))
            {
                prependSysPath0ForPyz(argv[1]);
                ret = runPyzFile(argv[1]);
            }
            else
            {
#if defined(SETUP_ARGV_BY_PYCONFIG)
                prependSysPath0(argv[1]);
#endif
                ret = runFile(argv[1]);
            }
        }
    }

    PyGILState_Ensure();

    if (PyErr_Occurred()) {
        ret = RET_FAIL;
        PyErr_Print();
    }

    // reference mod_wsgi & uwsgi finalize steps
    // https://github.com/GrahamDumpleton/mod_wsgi/blob/develop/src/server/wsgi_interp.c
    // https://github.com/unbit/uwsgi/blob/master/plugins/python/python_plugin.c
    PyObject *module = PyImport_ImportModule("atexit");
    Py_XDECREF(module);

    if (!PyImport_AddModule("dummy_threading")) {
        PyErr_Clear();
    }

    Py_Finalize();
    return ret;
}


void initPython(int argc, _CHAR *argv[]) {
#if defined(SETUP_ARGV_BY_LEGACY)
    #if defined(WIN32)
        Py_SetProgramName(argv[0]);
    #else
        int len = mbstowcs(NULL, argv[0], 0);
        wchar_t* arg0 = (wchar_t*) malloc(sizeof(wchar_t) * (len+1));
        mbstowcs(arg0, argv[0], len);
        arg0[len] = 0;
        Py_SetProgramName(arg0);
    #endif
#else
    PyStatus status;

    // ----------
    // PyPreConfig
    // ----------
    // On Windows platform invoke pyconcrete by subprocess may changed the console encoding to cp1252
    // force to set utf8 mode to avoid the issue.
    PyPreConfig preconfig;
    PyPreConfig_InitPythonConfig(&preconfig);
    preconfig.utf8_mode = 1;

    status = Py_PreInitialize(&preconfig);
    if (PyStatus_Exception(status)) {
        goto INIT_EXCEPTION;
    }

    // ----------
    // PyConfig
    // ----------
    PyConfig config;
    PyConfig_InitPythonConfig(&config);
    config.parse_argv = 0;
    config.isolated = 1;

    // Set program_name as pyconcrete. (Implicitly preinitialize Python)
    status = _PyConfig_SetString(&config, &config.program_name, argv[0]);
    if (PyStatus_Exception(status)) {
        goto INIT_EXCEPTION;
    }

    // Decode command line arguments. (Implicitly preinitialize Python)
    status = _PyConfig_SetArgv(&config, argc-1, argv+1);
    if (PyStatus_Exception(status))
    {
        goto INIT_EXCEPTION;
    }

    status = Py_InitializeFromConfig(&config);
    if (PyStatus_Exception(status))
    {
        goto INIT_EXCEPTION;
    }
    PyConfig_Clear(&config);
    return;

INIT_EXCEPTION:
    PyConfig_Clear(&config);
    if (PyStatus_IsExit(status))
    {
        return status.exitcode;
    }
    // Display the error message and exit the process with non-zero exit code
    Py_ExitStatusException(status);
#endif // SETUP_ARGV_BY_LEGACY
}


int createAndInitPyconcreteModule()
{
    int ret = 0;
    PyObject* module_name = PyUnicode_FromString("pyconcrete");
    PyObject* module = PyModule_New("pyconcrete");
    PyObject* module_dict = PyModule_GetDict(module);

    // Ensure built-ins are available in the module dict
    PyDict_SetItemString(module_dict, "__builtins__", PyEval_GetBuiltins());

    // assign module dict into run_string result
    PyObject* module_result = PyRun_String(pyconcrete_py_source, Py_file_input, module_dict, module_dict);
    if (!module_result)
    {
        PyErr_Print();
        ret = -1;
        goto ERROR;
    }

    // Add the module to sys.modules, making it available for import
    PyObject* sys_modules = PyImport_GetModuleDict();
    PyDict_SetItem(sys_modules, module_name, module);

    // Import the module to initialize pyconcrete file loader
    PyObject* imported_module = PyImport_ImportModule("pyconcrete");

ERROR:
    Py_XDECREF(imported_module);
    Py_XDECREF(module);
    Py_XDECREF(module_result);
    Py_XDECREF(module_name);
    Py_XDECREF(module_dict);
    return ret;
}


int runFile(const _CHAR* filepath)
{
    PyObject* py_filepath = getFullPath(filepath);
    PyObject* pyconcrete_mod = PyImport_ImportModule("pyconcrete");
    PyObject* run_pye_func = PyObject_GetAttrString(pyconcrete_mod, "run_pye");
    PyObject* args = Py_BuildValue("(O)", py_filepath);
    PyObject* result = PyObject_CallObject(run_pye_func, args);
    int ret = (result == NULL) ? RET_FAIL : RET_OK;
    Py_XDECREF(result);
    Py_XDECREF(args);
    Py_XDECREF(run_pye_func);
    Py_XDECREF(pyconcrete_mod);
    Py_XDECREF(py_filepath);
    return ret;
}


/*
    PySys_SetArgv is deprecated since python 3.11. It's original behavior will insert script's directory into sys.path.
    It's replace by PyConfig, but PyConfig only update sys.path when executing Py_Main or Py_RunMain.
    So it's better to update sys.path by pyconcrete.
 */
int prependSysPath0(const _CHAR* script_path)
{
    // script_dir = os.path.dirname(script_path)
    // sys.path.insert(0, script_dir)
    int ret = RET_OK;

    PyObject* py_script_path = getFullPath(script_path);
    PyObject* path_module = PyImport_ImportModule("os.path");
    PyObject* dirname_func = PyObject_GetAttrString(path_module, "dirname");
    PyObject* args = Py_BuildValue("(O)", py_script_path);
    PyObject* script_dir = PyObject_CallObject(dirname_func, args);

    PyObject* sys_path = PySys_GetObject("path");
    if (PyList_Insert(sys_path, 0, script_dir) < 0) {
        ret = RET_FAIL;
    }

    Py_XDECREF(py_script_path);
    Py_XDECREF(path_module);
    Py_XDECREF(dirname_func);
    Py_XDECREF(args);
    Py_XDECREF(script_dir);
    return ret;
}


int isZipFile(const _CHAR* filepath)
{
    FILE* f = _fopen(filepath, _T("rb"));
    if (f == NULL) return 0;
    unsigned char magic[4];
    size_t n = fread(magic, 1, 4, f);
    fclose(f);
    return (n == 4 && magic[0] == 0x50 && magic[1] == 0x4B
            && magic[2] == 0x03 && magic[3] == 0x04);
}


int prependSysPath0ForPyz(const _CHAR* pyz_path)
{
    PyObject* py_pyz_path = getFullPath(pyz_path);
    PyObject* sys_path = PySys_GetObject("path");
    int ret = (PyList_Insert(sys_path, 0, py_pyz_path) < 0) ? RET_FAIL : RET_OK;
    Py_XDECREF(py_pyz_path);
    return ret;
}


int runPyzFile(const _CHAR* filepath)
{
    int ret = RET_OK;
    PyObject* py_filepath = getFullPath(filepath);
    PyObject* pyconcrete_mod = PyImport_ImportModule("pyconcrete");
    PyObject* result = PyObject_CallMethod(pyconcrete_mod, "run_pyz", "(O)", py_filepath);
    if (result == NULL) {
        ret = RET_FAIL;
        PyErr_Print();
    }
    Py_XDECREF(result);
    Py_XDECREF(pyconcrete_mod);
    Py_XDECREF(py_filepath);
    return ret;
}


PyObject* getFullPath(const _CHAR* filepath)
{
    // import os.path
    // return os.path.abspath(filepath)
    PyObject* path_module = PyImport_ImportModule("os.path");
    PyObject* abspath_func = PyObject_GetAttrString(path_module, "abspath");
    PyObject* py_filepath = _PyUnicode_FromStringAndSize(filepath, _strlen(filepath));
    PyObject* args = Py_BuildValue("(O)", py_filepath);
    PyObject* py_file_abspath = PyObject_CallObject(abspath_func, args);

    Py_XDECREF(path_module);
    Py_XDECREF(abspath_func);
    Py_XDECREF(py_filepath);
    Py_XDECREF(args);
    return py_file_abspath;
}
