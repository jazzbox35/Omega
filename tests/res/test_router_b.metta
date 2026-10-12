(= (test_router_b $request $catalogue $last_outcome) ("Test" "b"))

(= (loadOmegaPlugin)
   (registerLLMRouter "test_router_b" test_router_b))
