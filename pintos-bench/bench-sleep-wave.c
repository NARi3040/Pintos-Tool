/* thread-viz 벤치 (공식 테스트 아님, make check에 안 들어감).
   priority가 제각각인 스레드 12개가 같은 tick을 목표로 잠들었다가 한꺼번에 깨어나는 것을 여러 번 반복함
   그동안 가장 낮은 main은 쉬지 않고 돌아서, 깨어난 스레드가 main을 바로 선점하는지가 드러남
   (sleep_list 처리, 깨운 직후 선점, busy wait 여부).
   테스트 자체 검사: 같은 tick에 깨어난 스레드는 priority가 높은 순서대로 실행돼야 함. */

#include <stdint.h>
#include <stdio.h>
#include "tests/threads/tests.h"
#include "threads/init.h"
#include "threads/interrupt.h"
#include "threads/synch.h"
#include "threads/thread.h"
#include "devices/timer.h"

#define N 12
#define ROUNDS 4
#define GAP 5

static int64_t start;
static int order[ROUNDS][N];   /* 라운드별로 깨어나서 실행된 순서대로 priority를 적음 */
static int count[ROUNDS];
static int finished;   /* 다 끝낸 스레드 수 */
static thread_func wave_thread;

void
test_bench_sleep_wave (void)
{
  int i, r;

  ASSERT (!thread_mlfqs);

  thread_set_priority (PRI_MAX);
  /* 첫 목표 tick을 넉넉히 뒤로 잡아서 모든 스레드가 그 전에 잠들게 함 */
  start = timer_ticks () + 10;
  for (i = 0; i < N; i++)
    {
      int priority = PRI_MIN + 5 + (i * 5) % N * 4;   /* 5와 N은 서로소 */
      char name[16];
      snprintf (name, sizeof name, "wave %d", priority);
      thread_create (name, priority, wave_thread, (void *) (intptr_t) priority);
    }
  thread_set_priority (PRI_MIN);

  /* 잠들지 않고 계속 돎. 깨어난 스레드가 선점하지 않으면 다음 타임슬라이스까지 main이 계속 실행됨 */
  while (finished < N)
    barrier ();

  for (r = 0; r < ROUNDS; r++)
    for (i = 1; i < N; i++)
      if (order[r][i] > order[r][i - 1])
        fail ("%d번째 파도: priority %d가 %d보다 먼저 실행됨", r + 1,
              order[r][i - 1], order[r][i]);
}

static void
wave_thread (void *aux)
{
  int priority = (intptr_t) aux;
  int r;

  for (r = 0; r < ROUNDS; r++)
    {
      enum intr_level old_level;

      timer_sleep (start + (int64_t) GAP * r - timer_ticks ());
      old_level = intr_disable ();
      order[r][count[r]++] = priority;
      intr_set_level (old_level);
    }
  enum intr_level old_level = intr_disable ();
  finished++;
  intr_set_level (old_level);
}
