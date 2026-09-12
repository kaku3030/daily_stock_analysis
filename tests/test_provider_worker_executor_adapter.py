"""Frozen Slice C authority matrix."""
from datetime import datetime, timezone
import logging
import pytest
from src.services.live_feed.commands import ProviderCommandType
from src.services.live_feed.controller import LiveFeedController, run_command_worker_once
from src.services.live_feed.provider_worker_contracts import ProviderExecutionOutcome, ResolvedProviderCommandOutcome
from src.services.live_feed.provider_worker_executor_adapter import ExecutorAdapter
from src.services.live_feed.provider_worker_supervisor import CommandInFlightError
import threading

NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)

class Sup:
    def __init__(self, error=None): self.error, self.calls = error, []
    def submit_command(self, command, *, payload=None):
        self.calls.append(command)
        if self.error: raise self.error
        return ResolvedProviderCommandOutcome(runtime_instance_id=command.runtime_instance_id, provider_id=command.provider_id, worker_generation=1, command=command, outcome=ProviderExecutionOutcome.SUCCEEDED, dispatched_at_monotonic_ns=1, terminal_observed_at_monotonic_ns=2, terminal_at_utc=NOW)

def stack(error=None):
    sup=Sup(error); adapter=ExecutorAdapter(supervisor=sup); controller=LiveFeedController(runtime_instance_id="r", provider_id="p", command_executor=adapter); adapter.attach_controller(controller); return sup, controller, adapter
def cmd(c): return c.submit_command(ProviderCommandType.SUBSCRIBE)

def test_01_nonblocking_local_acceptance_and_peek_submit_ack():
    s,c,a=stack(); x=cmd(c); a.start(); assert run_command_worker_once(c,a)==1; a.stop(join_timeout_seconds=2); assert [q.command_id for q in s.calls]==[x.command_id]
def test_02_controller_pump_is_capacity_one():
    s,c,a=stack(); first,second=cmd(c),cmd(c); a.start(); assert run_command_worker_once(c,a)==1; assert c.peek_command_for_worker().command_id==second.command_id; a.stop(join_timeout_seconds=2)
def test_03_adapter_token_rejects_second_local_command():
    s,c,a=stack(); first,second=cmd(c),cmd(c); a.submit(first)
    with pytest.raises(CommandInFlightError): a.submit(second)
def test_04_submit_does_not_call_supervisor():
    s,c,a=stack(); a.submit(cmd(c)); assert s.calls==[]

def test_04b_capacity_token_survives_in_flight_supervisor_resolution():
    entered = threading.Event(); release = threading.Event()
    class BlockingSup(Sup):
        def submit_command(self, command, *, payload=None):
            entered.set(); assert release.wait(2); return super().submit_command(command, payload=payload)
    s=BlockingSup(); a=ExecutorAdapter(supervisor=s); c=LiveFeedController(runtime_instance_id="r", provider_id="p", command_executor=a); a.attach_controller(c)
    first, second = cmd(c), cmd(c); a.start(); assert run_command_worker_once(c,a)==1; assert entered.wait(2)
    with pytest.raises(CommandInFlightError): a.submit(second)
    release.set(); a.stop(join_timeout_seconds=2)
def test_05_unexpected_exception_is_fail_loud_no_result(caplog):
    s,c,a=stack(RuntimeError("boom")); x=cmd(c); a.start(); run_command_worker_once(c,a); a.stop(join_timeout_seconds=2); assert a.is_dead and c.command_results==(); assert x.command_id in caplog.text
def test_06_no_replay_after_dispatcher_death():
    s,c,a=stack(RuntimeError("boom")); first,second=cmd(c),cmd(c); a.start(); run_command_worker_once(c,a); a.stop(join_timeout_seconds=2); assert [q.command_id for q in c.drain_commands_for_worker()]==[second.command_id]
def test_07_shutdown_handshake_is_deterministic():
    s,c,a=stack(); cmd(c); a.start(); run_command_worker_once(c,a); a.stop(join_timeout_seconds=2); a.stop(join_timeout_seconds=2); assert not a.is_running
def test_08_result_contract_preserved():
    s,c,a=stack(); cmd(c); a.start(); run_command_worker_once(c,a); a.stop(join_timeout_seconds=2); c.process_pending(); assert c.command_results[0].provider_execution_outcome==ProviderExecutionOutcome.SUCCEEDED.value
def test_09_no_synthetic_terminal_on_fault():
    s,c,a=stack(RuntimeError("fatal")); cmd(c); a.start(); run_command_worker_once(c,a); a.stop(join_timeout_seconds=2); assert c.command_results==()
def test_10_invalid_submit_rejected():
    _,_,a=stack()
    with pytest.raises(ValueError): a.submit(object())
def test_11_ack_mismatch_preserves_head():
    _,c,_=stack(); x=cmd(c)
    with pytest.raises(RuntimeError): c.ack_command_for_worker("wrong")
    assert c.peek_command_for_worker().command_id==x.command_id
def test_12_ack_removes_only_claimed_head():
    _,c,_=stack(); x=cmd(c); c.ack_command_for_worker(x.command_id); assert c.peek_command_for_worker() is None
