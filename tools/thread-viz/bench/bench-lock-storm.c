/* thread-viz 벤치 (공식 테스트 아님, make check에 안 들어감).
   priority가 제각각인 스레드 10개가 락 두 개(A -> B 순서로 중첩)를 두고 여러 번 경쟁함.
   락을 쥔 채 잠들어서 낮은 스레드가 락을 쥐고 높은 스레드가 기다리는 상황이 계속 생김
   (donation, 중첩 donation, 락 넘겨주기 순서).
   테스트 자체 검사: 락을 다 놓은 뒤엔 priority가 원래 값으로 돌아와야 함. */

#include <stdint.h>
#include <stdio.h>
#include "tests/threads/tests.h"
#include "threads/init.h"
#include "threads/synch.h"
#include "threads/thread.h"
#include "devices/timer.h"

#define N 10
#define ROUNDS 3

static struct lock a, b;
static struct semaphore done;
static thread_func storm_thread;

void
test_bench_lock_storm (void)
{
  int i;

  ASSERT (!thread_mlfqs);

  lock_init (&a);
  lock_init (&b);
  sema_init (&done, 0);

  /* 다 만든 뒤에 한꺼번에 경쟁시키려고 만드는 동안만 main을 최고 priority로 둠. */
  thread_set_priority (PRI_MAX);
  for (i = 0; i < N; i++)
    {
      /* 7과 N이 서로소라 (i * 7) % N은 0..N-1을 한 번씩 돎 -> priority가 섞인 순서로 만들어짐 */
      int priority = PRI_MIN + 10 + (i * 7) % N * 5;
      char name[16];
      snprintf (name, sizeof name, "storm %d", priority);
      thread_create (name, priority, storm_thread, (void *) (intptr_t) priority);
    }
  thread_set_priority (PRI_MIN);

  for (i = 0; i < N; i++)
    sema_down (&done);
}

static void
storm_thread (void *aux)
{
  int base = (intptr_t) aux;
  int r;

  for (r = 0; r < ROUNDS; r++)
    {
      lock_acquire (&a);
      lock_acquire (&b);
      timer_sleep (1);
      lock_release (&b);
      lock_release (&a);
      if (thread_get_priority () != base)
        fail ("%s: 락을 다 놓았는데 priority %d (원래 %d)", thread_name (),
              thread_get_priority (), base);
      timer_sleep (1 + base % 3);
    }
  sema_up (&done);
}
