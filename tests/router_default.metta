!(import! &self ./tests/lib/utils)
!(import! &self ./src/utils)
!(import! &self ../src/logger.py)
!(import! &self ./src/log)
!(import! &self ../src/config.py)
!(import! &self ./src/config)
!(import! &self ./src/plugin)
!(import! &self ../src/providers.py)
!(import! &self ./src/providers)

!(initLogger)

; R7-T1: the test's own keywords (zzkeyword, error) and threshold (4), from
; tests/res/router_default.yaml; expected values from that setup, not from
; routers/default.metta.

(= (command-line) ("config=./tests/res/router_default.yaml"))
!(initConfig)
!(test (loadPlugin (metta "default" "./routers")) ())

(= (catalogue) (("Test" "econ-1") ("Test" "prem-1")))

!(test (default_router_text "role_user what is the time" (catalogue)) ("Test" "econ-1"))
!(test (default_router_text "role_user use zzkeyword" (catalogue)) ("Test" "prem-1"))
!(test (default_router_text "role_user x role_tool error connecting" (catalogue)) ("Test" "prem-1"))
; whole-token: errors is not error
!(test (default_router_text "role_user x role_tool errors" (catalogue)) ("Test" "econ-1"))
; the >= boundary on user-plus-tool messages
!(test (default_router_text "role_user a role_tool b role_tool c" (catalogue)) ("Test" "econ-1"))
!(test (default_router_text "role_user a role_tool b role_tool c role_tool d" (catalogue)) ("Test" "prem-1"))
!(test (default_router_text "role_user a role_tool b role_tool c role_tool d role_tool e" (catalogue)) ("Test" "prem-1"))
; the known quirk, pinned: role_user written inside user text counts as a message
!(test (default_router_text "role_user see role_user here role_tool b role_tool c" (catalogue)) ("Test" "prem-1"))

; R7-T6: no prompt_atom survives a call, after two calls.
!(test (progn (default_router_text "role_user a" (catalogue))
              (default_router_text "role_user zzkeyword" (catalogue))
              (collapse (match &temp (prompt_atom $x $y) $x)))
       ())
