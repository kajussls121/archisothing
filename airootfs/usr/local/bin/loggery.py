import logging
def hprint(msg:str, loglevel:str, handler, loggername="loggery"):
    """
    Print and log a message using the specified log level.

    msg: message
    loglevel: "error", "debug", "critical", "exception", "warning", "info", other will default to info
    handler: None or logging.Handler
    loggername: Name used for logging, default is loggery
    """
    # Print to console
    print(str(loglevel).upper() + ": " + str(msg))

    if not handler: return # if None, exit
    logger = logging.getLogger(loggername)
    logger.setLevel(logging.DEBUG)  # Set logger level to ensure all messages are logged
    
    # Only add handler if it's not already added to this logger
    if handler not in logger.handlers:
        # Only set formatter if handler doesn't already have one
        if handler.formatter is None:
            dt_fmt = '%Y-%m-%d %H:%M:%S'
            formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
            handler.setFormatter(formatter)
        logger.addHandler(handler)

    if loglevel.lower() == "error": logger.error(msg)
    elif loglevel.lower() == "debug": logger.debug(msg)
    elif loglevel.lower() == "critical": logger.critical(msg)
    elif loglevel.lower() == "exception": logger.exception(msg)
    elif loglevel.lower() == "warning": logger.warning(msg)
    elif loglevel.lower() == "info": logger.info(msg)
    else: logger.info(msg)
    ## Determine log level number
    #if isinstance(loglevel, str):
    #    try:
    #        loglevel_num = getattr(logging, loglevel.upper())
    #    except AttributeError:
    #        loglevel_num = logging.INFO
    #else:
    #    loglevel_num = loglevel
    ## Make sure LOGGER is valid and loglevel_num is an int
    #if hasattr(LOGGER, 'log'):
    #    try:
    #        LOGGER.log(loglevel_num, str(msg))
    #    except Exception as e:
    #        print("ERROR: Failed logging: ", e)