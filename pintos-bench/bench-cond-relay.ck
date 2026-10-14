# -*- perl -*-
# thread-viz 벤치. 순서/priority 검사는 테스트 안에서 fail()로 함
use strict;
use warnings;
use tests::tests;
check_expected ([<<'EOT']);
(bench-cond-relay) begin
(bench-cond-relay) end
EOT
pass;
