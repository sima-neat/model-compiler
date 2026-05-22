<a id="afe-apis-sanitize-errors"></a>
# `afe.apis._sanitize_errors`

Source: `afe/apis/_sanitize_errors.py`

[Back to index](index.md)

Imports:
- `afe._tvm._defines.TVM_ERROR`
- [`afe.apis.defines.ExceptionFuncType`](afe-apis-defines.md#afe-apis-defines-exceptionfunctype)
- [`afe.apis.error_handling_variables`](afe-apis-error_handling_variables.md)
- `sima_utils.logging.sima_logger`

Functions:
- <a id="afe-apis-sanitize-errors-sanitize-exceptions"></a>`sanitize_exceptions(call_type: ExceptionFuncType)` (line 7): Provides exception handling. If a user is running our code it will not display full stacktrace, but some custom message. Used as a decorator to a function we want to sanitize.
    Parameters:
    - `call_from_tests`: bool. If true, errors will be raised normally. If False, exceptions are sanitized and displayed with custom messages.
    - `call_type`: ExceptionFuncType. Enum providing type of function we are handling. I.e. LOAD.
- <a id="afe-apis-sanitize-errors-sanitize-afe-error"></a>`sanitize_afe_error(default_message: str, exception: Exception)` (line 26)
    Parameters:
    - `default_message`: type `str`
    - `exception`: type `Exception`
- <a id="afe-apis-sanitize-errors-sanitize-tvm-error"></a>`sanitize_tvm_error(default_message: str, exception: Exception)` (line 51)
    Parameters:
    - `default_message`: type `str`
    - `exception`: type `Exception`
