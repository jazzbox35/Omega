!(import! &self ./tests/lib/utils)
!(import! &self ./src/utils)
!(import! &self ../src/logger.py)
!(import! &self ./src/log)
!(import! &self ./src/plugin)
!(import! &self ../src/providers.py)
!(import! &self ./src/providers)

!(initLogger)

; R6-T1: two routers register by name through the plugin loader, as entries
; of config/plugins.yaml do (loader: metta, location: routers/).

!(test (loadPlugin (metta "test_router_a" "./tests/res")) ())
!(test (loadPlugin (metta "test_router_b" "./tests/res")) ())

!(test (progn (llmRouterStart "test_router_a") (get-state &llmRouter)) test_router_a)
!(test (progn (llmRouterStart "test_router_b") (get-state &llmRouter)) test_router_b)

; No router configured: the null router, by the same lookup.
!(test (progn (llmRouterStart "") (get-state &llmRouter)) llmNullRouter)

; An unknown name halts startup: llmRouterStart raises, naming it and the
; registered routers.
!(test (case (catch (llmRouterStart "defualt")) (((Error $call $message) halted) ($_ started))) halted)
